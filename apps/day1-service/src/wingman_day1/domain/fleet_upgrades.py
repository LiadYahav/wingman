"""Every cluster's upgrade run, from the orchestrator's run list (ADR-0055's amendment).

The orchestrator lists the fleet's ``UpgradeClusterWorkflow`` runs, newest
first, with status and times only. A cluster's run id is
``upgrade-cluster-<file stem>`` and is reused by its next upgrade, and a run
continues-as-new after every step, so one id holds several entries: the
newest segment (open, or closed with how it ended), the
``continued_as_new`` segments of the same upgrade before it, and older
upgrades before those. One row per cluster is its newest upgrade, the
segments joined, started when its first segment started: the orchestrator's
own page folds them the same way.

Phases and ``waiting_for`` are not in the list: they come from reading the
run by its id, and only the first rows are read (open runs first).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from wingman_day1.domain.add_server import ListedRun
from wingman_day1.domain.upgrades import UPGRADE_WORKFLOW_PREFIX

CONTINUED: Final = "continued_as_new"
"""The status of a segment the run continued from: the same upgrade, still going on."""
OPEN: Final = "running"
_OLDEST: Final = datetime.min.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class FleetRun:
    """One cluster's newest upgrade, as the run list shows it."""

    workflow_id: str
    status: str
    """The newest segment's status, lowercase: ``running`` while the upgrade is open."""
    started_at: datetime | None
    """When the upgrade's first segment started."""
    closed_at: datetime | None

    @property
    def cluster(self) -> str:
        """The cluster file's stem the run upgrades."""
        return self.workflow_id.removeprefix(UPGRADE_WORKFLOW_PREFIX)

    @property
    def open(self) -> bool:
        """Whether the upgrade is still going on."""
        return self.status == OPEN


def _newest_first(entries: Sequence[ListedRun]) -> list[ListedRun]:
    return sorted(entries, key=lambda e: e.started_at or _OLDEST, reverse=True)


def _joined(entries: Sequence[ListedRun]) -> FleetRun:
    """The newest upgrade of one id: its newest segment, and the continued ones before it."""
    newest, *older = _newest_first(entries)
    started = newest.started_at
    for segment in older:
        if segment.status != CONTINUED:
            break
        started = segment.started_at or started
    return FleetRun(newest.workflow_id, newest.status, started, newest.closed_at)


def newest_upgrades(listed: Sequence[ListedRun]) -> list[FleetRun]:
    """One row per cluster, open upgrades first, then the newest started first.

    Entries whose id is not an upgrade run's are left out.
    """
    by_id: dict[str, list[ListedRun]] = {}
    for entry in listed:
        if entry.workflow_id.startswith(UPGRADE_WORKFLOW_PREFIX):
            by_id.setdefault(entry.workflow_id, []).append(entry)
    rows = [_joined(entries) for entries in by_id.values()]
    rows.sort(key=lambda row: row.started_at or _OLDEST, reverse=True)
    return sorted(rows, key=lambda row: not row.open)
