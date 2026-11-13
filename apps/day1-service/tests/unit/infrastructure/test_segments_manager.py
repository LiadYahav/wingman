"""HttpSegmentLedger against segments-manager's answers (MockTransport), its cache and its fake."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import yaml
from prometheus_client import CollectorRegistry

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import SegmentsManagerUnavailableError
from wingman_day1.domain.network import SegmentRecord, file_network, segment_of
from wingman_day1.infrastructure.cached_segments_manager import CachedSegmentLedger
from wingman_day1.infrastructure.fake_segments import (
    FakeSegmentLedger,
    default_segments_file,
    load_segments,
)
from wingman_day1.infrastructure.segments_manager import HttpSegmentLedger

SEGMENT = "10.20.90.0/24"
# One segment exactly as segments-manager's GET /api/segments/by-segment answers it.
BODY: dict[str, Any] = {
    "_id": "6720f0000000000000000999",
    "type": "HC",
    "site": "site2",
    "vlan_id": 2490,
    "epg_name": "EPG_site2_HC_2490",
    "segment": SEGMENT,
    "dhcp": True,
    "cluster_name": "ocp4-prep-amit-site2-a",
    "allocated_at": "2026-10-12T12:00:00+00:00",
    "status": "Allocated",
    "segment_connectivity_requests": None,
}
PARSED = SegmentRecord(
    segment=SEGMENT,
    vlan_id=2490,
    epg_name="EPG_site2_HC_2490",
    cluster_name="ocp4-prep-amit-site2-a",
    status="Allocated",
    type="HC",
    site="site2",
    dhcp=True,
    allocated_at="2026-10-12T12:00:00+00:00",
)

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
        timeout_seconds=2.0,
        metrics=metrics,
        transport=httpx.MockTransport(record),
        timer=iter(range(1000)).__next__,
    )
    return ledger, requests


def reply(status: int, body: object = None) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


async def test_one_segment_is_read_by_its_cidr_without_a_token() -> None:
    ledger, requests = make(reply(200, BODY))
    assert await ledger.segment(SEGMENT) == PARSED
    (request,) = requests
    assert (request.method, request.url.path) == ("GET", "/api/segments/by-segment")
    assert request.url.params["segment"] == SEGMENT
    assert request.url.host == "segments-manager.example"
    assert "authorization" not in request.headers
    await ledger.aclose()


async def test_an_unknown_segment_is_none() -> None:
    ledger, _ = make(reply(404, {"detail": "Segment not found"}))
    assert await ledger.segment(SEGMENT) is None


async def test_a_shared_upi_segment_lists_its_clusters_and_a_free_one_none() -> None:
    upi = {**BODY, "type": "UPI", "cluster_name": ["seed-a", "seed-b"]}
    ledger, _ = make(reply(200, upi))
    shared = await ledger.segment(SEGMENT)
    assert shared is not None
    assert shared.cluster_name == ("seed-a", "seed-b")
    free = {**BODY, "type": None, "cluster_name": None, "status": "Available"}
    ledger, _ = make(reply(200, free))
    record = await ledger.segment(SEGMENT)
    assert record is not None
    assert (record.cluster_name, record.type, record.status) == (None, None, "Available")


@pytest.mark.parametrize("status", [400, 401, 403, 422, 500, 502, 503])
async def test_any_other_answer_is_unavailable_not_none(status: int) -> None:
    ledger, _ = make(reply(status, {}))
    with pytest.raises(SegmentsManagerUnavailableError, match=f"answered {status}"):
        await ledger.segment(SEGMENT)


@pytest.mark.parametrize("exc", [httpx.ConnectError, httpx.ReadTimeout])
async def test_transport_failures_are_unavailable_and_name_no_host(
    exc: type[httpx.TransportError],
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exc("boom segments-manager.example", request=request)

    ledger, _ = make(fail)
    with pytest.raises(SegmentsManagerUnavailableError, match=exc.__name__) as caught:
        await ledger.segment(SEGMENT)
    assert "example" not in str(caught.value)


@pytest.mark.parametrize(
    "body",
    [
        ["not", "an", "object"],
        {**BODY, "segment": None},
        {**BODY, "segment": ""},
        {**BODY, "vlan_id": "2490"},
        {**BODY, "vlan_id": True},
        {**BODY, "epg_name": 7},
        {**BODY, "cluster_name": [1, 2]},
        {**BODY, "cluster_name": {"a": 1}},
        {**BODY, "status": False},
    ],
)
async def test_a_malformed_segment_is_unavailable(body: object) -> None:
    ledger, _ = make(reply(200, body))
    with pytest.raises(SegmentsManagerUnavailableError, match="malformed"):
        await ledger.segment(SEGMENT)


async def test_an_answer_for_another_segment_is_unavailable() -> None:
    ledger, _ = make(reply(200, {**BODY, "segment": "10.20.91.0/24"}))
    with pytest.raises(SegmentsManagerUnavailableError, match=r"answered segment 10\.20\.91\.0/24"):
        await ledger.segment(SEGMENT)


async def test_calls_are_counted_by_operation_and_outcome() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    for handler in (reply(200, BODY), reply(404, {}), reply(503, {})):
        ledger, _ = make(handler, metrics=metrics)
        with contextlib.suppress(SegmentsManagerUnavailableError):
            await ledger.segment(SEGMENT)

    def count(outcome: str) -> float | None:
        labels = {"dependency": "segments_manager", "operation": "get_segment", "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert count("ok") == 2, "an unknown segment is an answer: ok"
    assert count("unavailable") == 1


async def test_the_cache_keeps_answers_including_none_but_not_failures() -> None:
    fake = FakeSegmentLedger([PARSED])
    cached = CachedSegmentLedger(fake, TtlCache(), ttl=30)
    assert await cached.segment(SEGMENT) == PARSED
    assert await cached.segment(SEGMENT) == PARSED
    assert await cached.segment("10.20.91.0/24") is None
    assert await cached.segment("10.20.91.0/24") is None
    assert fake.reads == 2

    down = FakeSegmentLedger([PARSED], unavailable=True)
    cached = CachedSegmentLedger(down, TtlCache(), ttl=30)
    with pytest.raises(SegmentsManagerUnavailableError):
        await cached.segment(SEGMENT)
    down.unavailable = False
    assert await cached.segment(SEGMENT) == PARSED


def test_the_demo_ledger_agrees_with_the_fixture_clusters_but_herzi() -> None:
    """dev/fleet-fixtures/segments.yaml and dev/gitlab-fixtures tell one story."""
    records = {r.segment: r for r in load_segments(default_segments_file())}
    root = default_segments_file().parents[1] / "gitlab-fixtures/gitops-day1/platform-config/sites"
    files = sorted(root.glob("*/mces/*/hostedClusters/*.yaml"))
    assert files
    seen: dict[str, str] = {}
    for path in files:
        values = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        dhcp = values.get("dhcp_values") or {}
        if "network" not in dhcp:
            continue
        assert "vlanId" in values, f"{path.name}: allocate-segment writes vlanId with dhcp_values"
        file = file_network(values["vlanId"], dhcp["network"])
        assert file.segment is not None
        record = records[file.segment]
        seen[path.stem] = file.segment
        assert record.cluster_name == path.stem
        assert record.status == "Allocated"
        if path.stem == "ocp4-prod-herzi-site1":
            assert record.vlan_id != file.vlan_id, "the deliberate mismatch"
        else:
            assert record.vlan_id == file.vlan_id, path.stem
    assert "ocp4-prod-herzi-site1" in seen
    assert segment_of("10.20.48.0") in records, "a free segment, for the pool"
