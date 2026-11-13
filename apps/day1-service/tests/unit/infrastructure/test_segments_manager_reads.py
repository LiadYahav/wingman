"""The Segments area's reads (ADR-0047): the adapter's sites, stats, segments; cache; fake.

segments-manager's answers below are its own shapes (``src/api/routes.py``,
``StatsService.get_stats``), served by a MockTransport: nothing calls a network.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import SegmentsManagerUnavailableError
from wingman_day1.domain.network import SegmentRecord
from wingman_day1.domain.segments import SEGMENT_TYPES, SegmentList, SegmentQuery, TypeCount
from wingman_day1.infrastructure.cached_segments_manager import CachedSegmentLedger
from wingman_day1.infrastructure.fake_segments import (
    FakeSegmentLedger,
    default_segments_file,
    load_fake_ledger,
)
from wingman_day1.infrastructure.segments_manager import HttpSegmentLedger

HC: dict[str, Any] = {
    "_id": "6720f0000000000000000999",
    "type": "HC",
    "site": "site2",
    "vlan_id": 2490,
    "epg_name": "EPG_site2_HC_2490",
    "segment": "10.20.90.0/24",
    "dhcp": True,
    "cluster_name": "ocp4-prep-amit-site2-a",
    "allocated_at": "2026-10-12T12:00:00+00:00",
    "status": "Allocated",
}
UPI: dict[str, Any] = {
    **HC,
    "type": "UPI",
    "segment": "10.20.60.0/24",
    "dhcp": False,
    "cluster_name": ["ocp4-upi-a", "ocp4-upi-b"],
}
FREE: dict[str, Any] = {
    **HC,
    "type": None,
    "segment": "10.20.52.0/24",
    "cluster_name": None,
    "status": "Available",
    "segment_connectivity_requests": None,
}
STATS = [
    {
        "site": "site1",
        "total_segments": 20,
        "allocated": 1,
        "by_type": [
            {"type": kind, "allocated": int(kind == "INVENTORY")} for kind in SEGMENT_TYPES
        ],
    }
]

Handler = Callable[[httpx.Request], httpx.Response]


def make(
    handler: Handler, *, metrics: WingmanMetrics | None = None
) -> tuple[HttpSegmentLedger, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    ledger = HttpSegmentLedger(
        base_url="http://segments-manager.example/",
        metrics=metrics,
        transport=httpx.MockTransport(record),
        timer=iter(range(1000)).__next__,
    )
    return ledger, requests


def reply(status: int, body: object = None) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


async def test_the_sites_are_read_without_a_token_in_their_order() -> None:
    ledger, requests = make(reply(200, {"sites": ["site2", "site1", "site3"]}))
    assert await ledger.sites() == ("site2", "site1", "site3")
    (request,) = requests
    assert (request.method, request.url.path) == ("GET", "/api/sites")
    assert "authorization" not in request.headers


async def test_the_stats_are_typed_per_site_and_type() -> None:
    ledger, requests = make(reply(200, STATS))
    (site,) = await ledger.stats()
    assert (site.site, site.total_segments, site.allocated) == ("site1", 20, 1)
    assert site.by_type[2] == TypeCount("INVENTORY", 1)
    assert [count.type for count in site.by_type] == list(SEGMENT_TYPES)
    assert requests[0].url.path == "/api/stats"


async def test_the_segments_keep_segments_managers_values_and_filters() -> None:
    ledger, requests = make(reply(200, [HC, UPI, FREE]))
    query = SegmentQuery(site="site2", status="Allocated", type="HC")
    listing = await ledger.segments(query)
    assert listing.unreadable == ()
    hc, upi, free = listing.records
    assert hc == SegmentRecord(
        segment="10.20.90.0/24",
        vlan_id=2490,
        epg_name="EPG_site2_HC_2490",
        cluster_name="ocp4-prep-amit-site2-a",
        status="Allocated",
        type="HC",
        site="site2",
        dhcp=True,
        allocated_at="2026-10-12T12:00:00+00:00",
    )
    assert (upi.cluster_name, upi.dhcp) == (("ocp4-upi-a", "ocp4-upi-b"), False)
    assert (free.cluster_name, free.type, free.allocated_at) == (None, None, HC["allocated_at"])
    (request,) = requests
    assert request.url.path == "/api/segments"
    assert dict(request.url.params) == {"site": "site2", "status": "Allocated", "type": "HC"}


async def test_only_a_fresh_read_asks_for_fresh() -> None:
    ledger, requests = make(reply(200, []))
    await ledger.segments()
    await ledger.segments(fresh=True)
    assert [dict(r.url.params) for r in requests] == [{}, {"fresh": "true"}]


async def test_a_record_that_cannot_be_read_is_set_aside_and_the_rest_kept() -> None:
    no_segment = {k: v for k, v in HC.items() if k != "segment"}
    bad_vlan = {**HC, "segment": "10.20.91.0/24", "vlan_id": "2491"}
    bad_dhcp = {**HC, "segment": "10.20.92.0/24", "dhcp": "yes"}
    ledger, _ = make(reply(200, [no_segment, HC, bad_vlan, "nonsense", bad_dhcp]))
    listing = await ledger.segments()
    assert [r.segment for r in listing.records] == ["10.20.90.0/24"]
    assert listing.unreadable == (
        "segments-manager sent a segment Wingman could not read: it has no segment",
        "segments-manager sent segment 10.20.91.0/24 Wingman could not read: "
        "vlan_id is not a number",
        "segments-manager sent a segment Wingman could not read: a segment is not an object",
        "segments-manager sent segment 10.20.92.0/24 Wingman could not read: "
        "dhcp is not true or false",
    )


@pytest.mark.parametrize(
    ("read", "body"),
    [
        ("sites", ["site1"]),
        ("sites", {"sites": "site1"}),
        ("sites", {"sites": ["site1", 3]}),
        ("stats", {"site": "site1"}),
        ("stats", [{"site": "site1", "total_segments": "20", "allocated": 1}]),
        ("stats", [{"site": "site1", "total_segments": 20, "allocated": -1}]),
        ("stats", [{**STATS[0], "by_type": [{"type": "HC"}]}]),
        ("segments", {"segments": []}),
    ],
)
async def test_a_malformed_answer_is_unavailable(read: str, body: object) -> None:
    ledger, _ = make(reply(200, body))
    with pytest.raises(SegmentsManagerUnavailableError, match="malformed"):
        await getattr(ledger, read)()


@pytest.mark.parametrize("read", ["sites", "stats", "segments"])
@pytest.mark.parametrize("status", [404, 422, 500, 503])
async def test_any_answer_but_200_is_unavailable(read: str, status: int) -> None:
    ledger, _ = make(reply(status, {"detail": "nope"}))
    with pytest.raises(SegmentsManagerUnavailableError, match=f"answered {status}"):
        await getattr(ledger, read)()


@pytest.mark.parametrize("read", ["sites", "stats", "segments"])
async def test_unreachable_is_unavailable_and_names_no_host(read: str) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom segments-manager.example", request=request)

    ledger, _ = make(fail)
    with pytest.raises(SegmentsManagerUnavailableError, match="ConnectError") as caught:
        await getattr(ledger, read)()
    assert "example" not in str(caught.value)


async def test_each_read_is_counted_by_its_own_operation() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")

    def answer(request: httpx.Request) -> httpx.Response:
        bodies = {"/api/sites": {"sites": ["site1"]}, "/api/stats": STATS, "/api/segments": []}
        return httpx.Response(200, json=bodies[request.url.path])

    ledger, _ = make(answer, metrics=metrics)
    await ledger.sites()
    await ledger.stats()
    await ledger.segments()
    await ledger.segments(fresh=True)
    down, _ = make(reply(503, {}), metrics=metrics)
    with contextlib.suppress(SegmentsManagerUnavailableError):
        await down.segments(fresh=True)

    def count(operation: str, outcome: str) -> float | None:
        labels = {"dependency": "segments_manager", "operation": operation, "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert count("list_sites", "ok") == 1
    assert count("get_stats", "ok") == 1
    assert count("list_segments", "ok") == 1
    assert count("refresh_segments", "ok") == 1
    assert count("refresh_segments", "unavailable") == 1


# ── The cache ────────────────────────────────────────────────────────────────

FAKE_RECORD = SegmentRecord("10.20.90.0/24", 2490, "EPG", "ocp4-x", "Allocated", "HC", "site2")


async def test_the_cache_keeps_each_read_per_query_and_keeps_no_failure() -> None:
    fake = FakeSegmentLedger([FAKE_RECORD], sites=["site2"])
    cached = CachedSegmentLedger(fake, TtlCache(), ttl=10)
    for _ in range(2):
        assert await cached.sites() == ("site2",)
        assert len(await cached.stats()) == 1
        assert len((await cached.segments()).records) == 1
        assert (await cached.segments(SegmentQuery(site="site1"))).records == ()
    assert fake.list_reads == 4, "one read each: sites, stats, and two queries"
    # site1 and SITE1 are one query to segments-manager (it compares without case)
    await cached.segments(SegmentQuery(site="SITE1"))
    assert fake.list_reads == 4

    down = FakeSegmentLedger([FAKE_RECORD], unavailable=True)
    cached = CachedSegmentLedger(down, TtlCache(), ttl=10)
    with pytest.raises(SegmentsManagerUnavailableError):
        await cached.segments()
    down.unavailable = False
    assert len((await cached.segments()).records) == 1


async def test_a_fresh_read_forgets_every_segments_manager_answer_and_keeps_its_own() -> None:
    fake = FakeSegmentLedger([FAKE_RECORD], sites=["site2"])
    cached = CachedSegmentLedger(fake, TtlCache(), ttl=10)
    await cached.sites()
    await cached.stats()
    await cached.segment(FAKE_RECORD.segment)
    await cached.segments(SegmentQuery(status="Allocated"))
    assert (fake.list_reads, fake.reads) == (3, 1)

    assert isinstance(await cached.segments(fresh=True), SegmentList)
    assert fake.fresh_reads == 1
    await cached.segments()  # the fresh answer is kept: no read
    assert fake.list_reads == 4
    await cached.sites()
    await cached.stats()
    await cached.segment(FAKE_RECORD.segment)
    await cached.segments(SegmentQuery(status="Allocated"))
    assert (fake.list_reads, fake.reads) == (7, 2), "everything else is read again"


# ── The fake ─────────────────────────────────────────────────────────────────


async def test_the_fake_answers_like_segments_manager() -> None:
    fake = FakeSegmentLedger([FAKE_RECORD])
    assert await fake.sites() == ("site2",), "without sites: the records' sites"
    allocated = await fake.segments(SegmentQuery(site="SITE2", status="allocated", type="hc"))
    assert allocated.records == (FAKE_RECORD,)
    fake.unavailable = True
    for read in (fake.sites, fake.stats, fake.segments):
        with pytest.raises(SegmentsManagerUnavailableError):
            await read()


async def test_the_demo_ledger_has_every_type_a_site_without_segments_and_its_stats() -> None:
    ledger = load_fake_ledger(default_segments_file())
    assert await ledger.sites() == ("site1", "site2", "site3")
    stats = {s.site: s for s in await ledger.stats()}
    assert (stats["site3"].total_segments, stats["site3"].allocated) == (0, 0)
    assert [t.type for t in stats["site3"].by_type] == list(SEGMENT_TYPES)
    assert (stats["site1"].total_segments, stats["site1"].allocated) == (12, 10)
    assert {t.type: t.allocated for t in stats["site1"].by_type} == {
        "HC": 6,
        "MCE": 1,
        "INVENTORY": 1,
        "PXE": 1,
        "UPI": 1,
        "HUB": 0,
    }
    records = (await ledger.segments()).records
    assert {r.type for r in records} == {*SEGMENT_TYPES, None}
    upi = next(r for r in records if r.type == "UPI")
    assert upi.cluster_name == ("ocp4-upi-a", "ocp4-upi-b")
    assert any(r.dhcp is False for r in records)
    free = [r for r in records if r.status == "Available"]
    assert free and any(r.allocated_at for r in free), "a released segment keeps allocated_at"
    # A type never matches an Available segment: it has none
    assert all(
        r.status == "Allocated" for r in (await ledger.segments(SegmentQuery(type="HC"))).records
    )
