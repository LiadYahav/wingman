"""One row per cluster from the orchestrator's upgrade run list (ADR-0055's amendment)."""

from __future__ import annotations

from datetime import UTC, datetime

from wingman_day1.domain.add_server import ListedRun
from wingman_day1.domain.fleet_upgrades import newest_upgrades

LARK = "upgrade-cluster-ocp4-prod-lark-site1"
OWL = "upgrade-cluster-ocp4-prod-owl-site1"
HAWK = "upgrade-cluster-ocp4-prod-hawk-site1"


def at(hour: int) -> datetime:
    return datetime(2026, 11, 13, hour, 0, tzinfo=UTC)


def entry(workflow_id: str, status: str, hour: int, closed: int | None = None) -> ListedRun:
    return ListedRun(
        workflow_id, status, started_at=at(hour), closed_at=at(closed) if closed else None
    )


def test_an_upgrades_continued_segments_are_joined_and_it_started_with_the_first() -> None:
    [lark] = newest_upgrades(
        [
            entry(LARK, "running", 12),
            entry(LARK, "continued_as_new", 11, closed=12),
            entry(LARK, "continued_as_new", 10, closed=11),
            entry(LARK, "completed", 8, closed=9),  # the cluster's previous upgrade
        ]
    )
    assert (lark.cluster, lark.status, lark.open) == ("ocp4-prod-lark-site1", "running", True)
    assert lark.started_at == at(10)
    assert lark.closed_at is None


def test_a_closed_upgrade_keeps_how_its_newest_segment_ended() -> None:
    [owl] = newest_upgrades(
        [entry(OWL, "continued_as_new", 9, closed=10), entry(OWL, "failed", 10, closed=11)]
    )
    assert (owl.status, owl.open, owl.started_at, owl.closed_at) == ("failed", False, at(9), at(11))


def test_open_upgrades_come_first_then_the_newest_and_other_ids_are_left_out() -> None:
    rows = newest_upgrades(
        [
            entry(HAWK, "completed", 14, closed=15),
            entry(OWL, "running", 9),
            entry("upgrade-targets-ocp4-prod-owl-site1", "completed", 13, closed=13),
            entry(LARK, "running", 11),
        ]
    )
    assert [row.workflow_id for row in rows] == [LARK, OWL, HAWK]


def test_no_runs_is_no_rows() -> None:
    assert newest_upgrades([]) == []
