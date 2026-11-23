"""An InfraEnv's pool: the servers add-server-to-mce draws for it (ADR-0057's 3.54.0 amendment).

The platform's naming convention (2026-11-22): an InfraEnv is
``<flavor>-<mtl|kv<cpu>>-<zone>`` (``c200-mtl-az1``) and lists its flavor,
its size and its MCE's site as ``spec.agentLabels`` (``redbull.io/flavor``,
``redbull.io/size``, ``redbull.io/site``, and ``topology.kubernetes.io/zone``);
a server is ``ocp-<flavor>-<mtl|kv<cpu>>-<site>-<serial|mac>``. The zone is in
no server's name: it is where the server is cabled.

add-server-to-mce's pool draw (team-redbull/workflows ``29ef001``) names its
servers from the three labels, in that order: ``^ocp-<flavor>-<size>-<site>-``,
case as given, and fails the run when a label is missing or not one lowercase
word. It does not filter by zone, and server-scan records none, so neither
does Wingman: the InfraEnvs of one flavor and size in several zones of a site
draw from the same servers. A named install is not matched to the pool by the
workflow at all.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

NAME_PREFIX: Final = "ocp-"
"""What every server name starts with."""
POOL_LABELS: Final = ("redbull.io/flavor", "redbull.io/size", "redbull.io/site")
"""The agentLabels whose values a pool's server names carry after ``ocp-``, in that order."""
_POOL_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class InfraEnvObservation:
    """One InfraEnv on an MCE hub: its name and its ``spec.agentLabels``."""

    name: str
    agent_labels: Mapping[str, str] = field(default_factory=dict)


def pool_label_problems(agent_labels: Mapping[str, str]) -> tuple[str, ...]:
    """Why the labels cannot name a pool draw's servers (the workflow's words); empty: they can."""
    problems: list[str] = []
    for key in POOL_LABELS:
        value = agent_labels.get(key)
        if not value:
            problems.append(f"{key} is missing")
        elif not _POOL_WORD.fullmatch(value):
            problems.append(f"{key}={value!r} is not one lowercase word of letters and digits")
    return tuple(problems)


@dataclass(frozen=True, slots=True)
class Pool:
    """An InfraEnv as Inventory Management matches servers to it.

    ``server_prefix`` is ``ocp-<flavor>-<size>-<site>-`` from its agentLabels,
    or ``None`` when they are unknown (not read: live status off, the hub
    unreadable) or cannot name servers (``label_problems``: the workflow
    refuses a pool draw into it).
    """

    infra_env: str
    server_prefix: str | None = None
    label_problems: tuple[str, ...] = ()

    @classmethod
    def observed(cls, infra_env: InfraEnvObservation) -> Pool:
        """The pool of an InfraEnv read from its MCE, its labels judged."""
        labels = infra_env.agent_labels
        problems = pool_label_problems(labels)
        prefix = None if problems else "-".join(labels[key] for key in POOL_LABELS)
        return cls(
            infra_env.name,
            server_prefix=f"{NAME_PREFIX}{prefix}-" if prefix is not None else None,
            label_problems=problems,
        )

    @classmethod
    def unread(cls, infra_env: str) -> Pool:
        """A pool whose InfraEnv's labels Wingman could not read: its servers' names are unknown."""
        return cls(infra_env)

    def names(self, server: str) -> bool:
        """Whether a pool draw into it could take a server of this name (case as given)."""
        return self.server_prefix is not None and server.startswith(self.server_prefix)
