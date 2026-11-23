"""What herzi says about an InfraEnv pool, on the InfraEnv itself (herzi ``main``, ``0ef4d2a``).

herzi, one per MCE hub, keeps each InfraEnv's spare Agents in step with its
NodePools' demand. It owns no object with a status; what it marks, or is
told, sits on the InfraEnv Wingman already lists (its ``docs/ops/operating.md``):

- the label ``herzi.redbull.io/ignore`` (any value; herzi's default
  ``ignoreLabel``): herzi does not read the pool at all, and orders nothing;
- the annotation ``herzi.redbull.io/paused: "true"``: herzi observes the
  pool and orders nothing (its plan to retire used servers also removes
  nothing from a paused pool, its rule 7);
- ``herzi.redbull.io/blocked-until`` (RFC 3339, written before every order):
  an order in flight, or one whose outcome was unclear; herzi orders nothing
  more there until then;
- ``herzi.redbull.io/state`` (JSON, at most 1 KiB): ``capFailAt``, its last
  order that found no hardware, and ``lastOKAt``, the last proof it
  recovered. A capacity failure newer than the proof means herzi is
  probing for hardware, one server at a time.

herzi's config may also exclude or pause a pool, or keep it in dry run;
Wingman cannot see that (it is herzi's ConfigMap), nor herzi's metrics.
Malformed marks are read as none: they are herzi's, and only shown.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

IGNORE_LABEL: Final = "herzi.redbull.io/ignore"
PAUSED: Final = "herzi.redbull.io/paused"
BLOCKED_UNTIL: Final = "herzi.redbull.io/blocked-until"
STATE: Final = "herzi.redbull.io/state"
MAX_STATE: Final = 1024
"""herzi reads a longer state as none, and so does Wingman."""
_FRACTION = re.compile(r"(\.\d{6})\d+")


@dataclass(frozen=True, slots=True)
class HerziMarks:
    """herzi's marks on one InfraEnv; none set: herzi manages it as any other."""

    ignored: bool = False
    paused: bool = False
    blocked_until: datetime | None = None
    no_hardware_since: datetime | None = None
    """Its last order that found no hardware, when it has not recovered since."""

    @property
    def any(self) -> bool:
        """Whether herzi has said anything here."""
        return self.ignored or self.paused or bool(self.blocked_until or self.no_hardware_since)


def _moment(value: object) -> datetime | None:
    """An RFC 3339 time as herzi writes it (Go's ``time.Time``); ``None`` when it is not one."""
    if not isinstance(value, str) or not value or value.startswith("0001-"):
        return None
    try:
        found = datetime.fromisoformat(_FRACTION.sub(r"\1", value.replace("Z", "+00:00")))
    except ValueError:
        return None
    return found if found.tzinfo is not None else None


def _no_hardware(state: str | None) -> datetime | None:
    if not state or len(state) > MAX_STATE:
        return None
    try:
        parsed = json.loads(state)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    failed, recovered = _moment(parsed.get("capFailAt")), _moment(parsed.get("lastOKAt"))
    if failed is None or (recovered is not None and recovered >= failed):
        return None
    return failed


def herzi_marks(labels: Mapping[str, str], annotations: Mapping[str, str]) -> HerziMarks:
    """The marks on an InfraEnv, from its ``metadata.labels`` and ``metadata.annotations``."""
    return HerziMarks(
        ignored=IGNORE_LABEL in labels,
        paused=annotations.get(PAUSED) == "true",
        blocked_until=_moment(annotations.get(BLOCKED_UNTIL)),
        no_hardware_since=_no_hardware(annotations.get(STATE)),
    )
