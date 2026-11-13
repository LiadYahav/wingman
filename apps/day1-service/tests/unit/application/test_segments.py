"""SegmentsService: the Refresh cool-down; the day1 repo failing never fails the page (ADR-0047)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from wingman_core.domain.errors import GitUnavailableError, PermissionDeniedError
from wingman_day1.application.segments import FRESH_COOLDOWN_SECONDS, SegmentsService
from wingman_day1.domain.network import SegmentRecord
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.segments import Holder, SegmentQuery
from wingman_day1.infrastructure.fake_segments import FakeSegmentLedger

HERZI = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-herzi-site1")
RECORD = SegmentRecord("10.20.44.0/24", 1418, "EPG", HERZI.name, "Allocated", "HC", "site1")


class Clusters:
    """A ClusterService's ``clusters``: one file, or the day1 repo failing with ``error``."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def clusters(self) -> list[Any]:
        if self.error is not None:
            raise self.error
        return [SimpleNamespace(ref=HERZI)]


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def service(
    ledger: FakeSegmentLedger, clusters: Any = None, clock: Clock | None = None
) -> SegmentsService:
    source: Any = clusters if clusters is not None else Clusters()
    return SegmentsService(ledger, source, clock=clock or Clock())


async def test_the_segments_come_with_their_holders_linked_to_day1() -> None:
    view = await service(FakeSegmentLedger([RECORD])).segments()
    (row,) = view.rows
    assert row.holders == (Holder(HERZI.name, HERZI),)
    assert (view.clusters_error, view.fresh, view.unreadable) == (None, False, ())


async def test_the_query_is_segments_managers() -> None:
    ledger = FakeSegmentLedger([RECORD])
    assert (await service(ledger).segments(SegmentQuery(status="Available"))).rows == ()


async def test_a_fresh_read_is_honoured_once_per_cool_down() -> None:
    ledger, clock = FakeSegmentLedger([RECORD]), Clock()
    segments = service(ledger, clock=clock)
    assert (await segments.segments(fresh=True)).fresh is True
    clock.now += FRESH_COOLDOWN_SECONDS - 0.1
    assert (await segments.segments(fresh=True)).fresh is False, "held: answered as a normal read"
    assert ledger.fresh_reads == 1
    clock.now += 0.1
    assert (await segments.segments(fresh=True)).fresh is True
    assert (await segments.segments()).fresh is False
    assert ledger.fresh_reads == 2


async def test_the_day1_repo_failing_lists_the_segments_unlinked_with_the_reason() -> None:
    for error in (GitUnavailableError("GitLab answered 503"), PermissionDeniedError("no access")):
        view = await service(FakeSegmentLedger([RECORD]), Clusters(error)).segments()
        (row,) = view.rows
        assert row.holders == (Holder(HERZI.name, None),)
        assert view.clusters_error == f"{type(error).__name__.removesuffix('Error')}: {error}"


async def test_sites_and_stats_pass_through() -> None:
    ledger = FakeSegmentLedger([RECORD], sites=["site1", "site3"])
    segments = service(ledger)
    assert await segments.sites() == ("site1", "site3")
    assert [s.site for s in await segments.stats()] == ["site1", "site3"]
