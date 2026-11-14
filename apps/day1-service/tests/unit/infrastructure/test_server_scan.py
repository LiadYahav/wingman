"""HttpServerInventory against server-scan's answers (MockTransport), and its cache."""

from __future__ import annotations

import copy
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import (
    ServerNotFoundError,
    ServerScanDeniedError,
    ServerScanUnavailableError,
)
from wingman_day1.domain.server_scan_architecture import ArchitectureDiagram
from wingman_day1.domain.server_scan_events import EventPage
from wingman_day1.domain.server_scan_record import ServerRecord, VmHostAnswer
from wingman_day1.domain.server_scan_servers import FleetRows, MaintenanceStart, ServerMaintenance
from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.domain.server_scan_skill import Skill, SkillZip
from wingman_day1.domain.servers import ServerDetail, ServerRow
from wingman_day1.infrastructure.cached_server_scan import CachedServerInventory
from wingman_day1.infrastructure.fake_server_scan_sites import count_sites
from wingman_day1.infrastructure.server_scan import HttpServerInventory

TOKEN = "server-scan-viewer-token-never-shown-0001"
SERVER_ID = "srv_d226c05c968244e19f68e4aa8f16bad3"
# One row exactly as server-scan's GET /api/v1/servers/rows answers it.
ROW: dict[str, Any] = {
    "id": SERVER_ID,
    "name": "ocp-cisco-m6-bat-yam-128c-128gb-CIS0000630",
    "vendor": "cisco",
    "model": "UCS C220 M6",
    "site_id": "bat-yam",
    "source_provider": "INTERSIGHT",
    "installation_type": "HOSTED_CLUSTER",
    "health": "UNKNOWN",
    "maintenance": {"enabled": False, "reason": None, "created_by": None},
    "reservation": {
        "held": False,
        "holder": None,
        "mce_cluster": None,
        "infra_env": None,
        "expires_at": None,
    },
    "openshift_state": "INSTALLED",
    "cluster_name": "hc-bat-yam-03",
    "mce_name": "mce-bat-yam",
    "openshift_reported_name": None,
    "contested_with": None,
    "profile_template_name": "UCS-X-Standard",
    "last_seen_at": "2026-11-10T22:00:03.530203Z",
    "stale": False,
    "reachable": True,
    "serial": "CIS0000630",
    "bmc_host": "192.0.2.118",
    "macs": ["02:00:00:00:00:01", "02:00:00:00:00:02"],
}
PARSED = ServerRow(
    id=SERVER_ID,
    name="ocp-cisco-m6-bat-yam-128c-128gb-CIS0000630",
    state="INSTALLED",
    health="UNKNOWN",
    serial="CIS0000630",
    vendor="cisco",
    model="UCS C220 M6",
    site="bat-yam",
    cluster_name="hc-bat-yam-03",
    mce="mce-bat-yam",
    maintenance=False,
    reachable=True,
    stale=False,
    last_seen_at=datetime(2026, 11, 10, 22, 0, 3, 530203, tzinfo=UTC),
    reserved_by=None,
    macs=("02:00:00:00:00:01", "02:00:00:00:00:02"),
    installation_type="HOSTED_CLUSTER",
    source_provider="INTERSIGHT",
    profile_template="UCS-X-Standard",
    bmc_host="192.0.2.118",
)
DETAIL: dict[str, Any] = {
    "id": SERVER_ID,
    "name": "ocp-cisco-m6-bat-yam-128c-128gb-CIS0000630",
    "vendor": "cisco",
    "model": "UCS C220 M6",
    "site_id": "bat-yam",
    "health": {"overall": "UNKNOWN", "memory": "HEALTHY"},
    "maintenance": {"enabled": False},
    "reachable": True,
    "stale": False,
    "last_seen_at": "2026-11-10T22:00:03.530203Z",
    "reservation": None,
    "openshift": {
        "lifecycle_state": "INSTALLED",
        "cluster_name": "hc-bat-yam-03",
        "mce_name": "mce-bat-yam",
        "contested_with": None,
    },
}

Handler = Callable[[httpx.Request], httpx.Response]


def make(
    handler: Handler, *, token: str = TOKEN, metrics: WingmanMetrics | None = None
) -> tuple[HttpServerInventory, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    inventory = HttpServerInventory(
        base_url="http://server-scan-api.inventory.svc:8000/",
        token=token,
        timeout_seconds=2.0,
        metrics=metrics,
        transport=httpx.MockTransport(record),
        timer=iter(range(1000)).__next__,
    )
    return inventory, requests


def reply(status: int, body: object = None, **headers: str) -> Handler:
    return lambda _request: httpx.Response(status, json=body, headers=headers)


def rows_body(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"generated_at": "2026-11-11T08:00:00Z", "items": list(rows)}


async def test_the_fleet_is_read_as_rows_with_the_viewer_token() -> None:
    inventory, requests = make(reply(200, rows_body(ROW)))
    assert await inventory.rows() == [PARSED]
    request = requests[0]
    assert request.url.path == "/api/v1/servers/rows"
    assert request.url.host == "server-scan-api.inventory.svc"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    await inventory.aclose()


async def test_without_a_token_no_authorization_header_is_sent() -> None:
    inventory, requests = make(reply(200, rows_body()), token="")
    assert await inventory.rows() == []
    assert "authorization" not in requests[0].headers


async def test_maintenance_a_held_reservation_and_a_contested_claim_are_read() -> None:
    busy = copy.deepcopy(ROW)
    busy["maintenance"]["enabled"] = True
    busy["reservation"].update(
        held=True,
        holder="uninstall-server-from-hc",
        mce_cluster="ocp4-prod-mce-site1-a",
        infra_env="cisco-m6-bat-yam-128c-128gb",
        expires_at="2026-11-13T18:00:00Z",
    )
    busy["contested_with"] = "hc-bat-yam-02"
    busy["stale"], busy["reachable"] = True, False
    expired = copy.deepcopy(ROW)
    expired["reservation"].update(held=False, holder="install-server")
    bare = {**ROW, "maintenance": None, "reservation": None, "serial": None, "last_seen_at": None}
    inventory, _ = make(reply(200, rows_body(busy, expired, bare)))
    first, second, third = await inventory.rows()
    assert (first.maintenance, first.reserved_by, first.contested) == (
        True,
        "uninstall-server-from-hc",
        True,
    )
    assert (first.stale, first.reachable) == (True, False)
    assert (first.reserved_for_mce, first.reserved_for_infra_env) == (
        "ocp4-prod-mce-site1-a",
        "cisco-m6-bat-yam-128c-128gb",
    )
    assert first.reserved_until is not None and first.reserved_until.hour == 18
    assert second.reserved_by is None, "an expired lock is not held"
    assert (second.reserved_for_mce, second.reserved_until) == (None, None)
    assert (third.maintenance, third.serial, third.last_seen_at) == (False, None, None)


async def test_an_unchanged_fleet_is_revalidated_with_its_etag() -> None:
    answers = iter(
        [
            httpx.Response(200, json=rows_body(ROW), headers={"ETag": 'W/"fleet-1"'}),
            httpx.Response(304),
        ]
    )
    inventory, requests = make(lambda _r: next(answers))
    assert await inventory.rows() == [PARSED]
    assert await inventory.rows() == [PARSED]
    assert "if-none-match" not in requests[0].headers
    assert requests[1].headers["if-none-match"] == 'W/"fleet-1"'


async def test_a_304_without_a_copy_is_unavailable_not_empty() -> None:
    inventory, _ = make(reply(304))
    with pytest.raises(ServerScanUnavailableError, match="answered 304"):
        await inventory.rows()


@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_token_is_denied_and_names_the_setting(status: int) -> None:
    inventory, _ = make(reply(status, {"detail": f"bad token {TOKEN}"}))
    with pytest.raises(ServerScanDeniedError, match="SERVER_SCAN_TOKEN") as caught:
        await inventory.rows()
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize("status", [404, 500, 502, 503])
async def test_any_other_answer_is_unavailable_not_empty(status: int) -> None:
    inventory, _ = make(reply(status, {}))
    with pytest.raises(ServerScanUnavailableError, match=f"answered {status}") as caught:
        await inventory.rows()
    assert not isinstance(caught.value, ServerScanDeniedError)


@pytest.mark.parametrize("exc", [httpx.ConnectError, httpx.ReadTimeout])
async def test_transport_failures_are_unavailable(exc: type[httpx.TransportError]) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exc(f"boom {TOKEN}", request=request)

    inventory, _ = make(fail)
    with pytest.raises(ServerScanUnavailableError, match=exc.__name__) as caught:
        await inventory.rows()
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize(
    "body",
    [
        ["not", "an", "object"],
        {"generated_at": "x"},
        {"items": "nope"},
        {"items": ["nope"]},
        {"items": [{**ROW, "id": None}]},
        {"items": [{**ROW, "name": ""}]},
        {"items": [{**ROW, "openshift_state": None}]},
        {"items": [{**ROW, "reachable": "yes"}]},
        {"items": [{**ROW, "maintenance": "off"}]},
        {"items": [{**ROW, "last_seen_at": "yesterday"}]},
        {"items": [{**ROW, "macs": "02:00:00:00:00:01"}]},
    ],
)
async def test_malformed_rows_are_unavailable(body: object) -> None:
    inventory, _ = make(reply(200, body))
    with pytest.raises(ServerScanUnavailableError, match="malformed"):
        await inventory.rows()


async def test_one_server_is_read_by_its_id_encoded_into_one_segment() -> None:
    inventory, requests = make(reply(200, DETAIL))
    assert await inventory.server(SERVER_ID) == ServerDetail(
        SERVER_ID, "ocp-cisco-m6-bat-yam-128c-128gb-CIS0000630", "hc-bat-yam-03"
    )
    assert requests[0].url.path == f"/api/v1/servers/{SERVER_ID}"
    assert requests[0].headers["authorization"] == f"Bearer {TOKEN}"
    await inventory.server("odd/../id")
    assert requests[1].url.raw_path == b"/api/v1/servers/odd%2F..%2Fid"


async def test_a_server_in_no_cluster_has_no_cluster_name() -> None:
    inventory, _ = make(reply(200, {**DETAIL, "openshift": None}))
    assert (await inventory.server(SERVER_ID)).cluster_name is None


async def test_an_unknown_server_is_not_found() -> None:
    problem = {"type": "/problems/not-found", "status": 404, "code": "SERVER_NOT_FOUND"}
    inventory, _ = make(reply(404, problem))
    with pytest.raises(ServerNotFoundError, match="srv_nope"):
        await inventory.server("srv_nope")


@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (reply(500, {}), ServerScanUnavailableError),
        (reply(403, {}), ServerScanDeniedError),
        (reply(200, {"id": SERVER_ID}), ServerScanUnavailableError),
    ],
)
async def test_a_server_that_cannot_be_read_is_unavailable(
    handler: Handler, error: type[Exception]
) -> None:
    inventory, _ = make(handler)
    with pytest.raises(error):
        await inventory.server(SERVER_ID)


async def test_calls_are_counted_by_operation_and_outcome() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    ok, _ = make(reply(200, rows_body(ROW)), metrics=metrics)
    await ok.rows()
    denied, _ = make(reply(401, {}), metrics=metrics)
    with pytest.raises(ServerScanDeniedError):
        await denied.rows()
    missing, _ = make(reply(404, {}), metrics=metrics)
    with pytest.raises(ServerNotFoundError):
        await missing.server("srv_x")

    def count(operation: str, outcome: str) -> float | None:
        labels = {"dependency": "server_scan", "operation": operation, "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert count("list_server_rows", "ok") == 1
    assert count("list_server_rows", "denied") == 1
    assert count("get_server", "not_found") == 1


class CountingInventory:
    def __init__(self) -> None:
        self.row_reads = 0
        self.server_reads = 0
        self.site_reads = 0
        self.fail = False

    async def rows(self) -> list[ServerRow]:
        return list((await self.fleet()).rows)

    async def fleet(self) -> FleetRows:
        self.row_reads += 1
        if self.fail:
            raise ServerScanUnavailableError("down")
        return FleetRows(rows=(PARSED,), generated_at=None)

    async def server(self, server_id: str) -> ServerDetail:
        self.server_reads += 1
        return ServerDetail(server_id, "n", None)

    async def sites(self) -> FleetSites:
        self.site_reads += 1
        if self.fail:
            raise ServerScanUnavailableError("down")
        return count_sites([PARSED], [("bat-yam", "Bat Yam")])

    async def start_maintenance(self, server_id: str, start: MaintenanceStart) -> ServerMaintenance:
        raise AssertionError("not written here")

    async def end_maintenance(self, server_id: str) -> ServerMaintenance:
        raise AssertionError("not written here")

    async def record(self, server_id: str) -> ServerRecord:
        raise AssertionError("not read here")

    async def vm_host(self, server_id: str) -> VmHostAnswer:
        raise AssertionError("not read here")

    async def server_events(
        self, server_id: str, *, cursor: str | None, page_size: int
    ) -> EventPage:
        raise AssertionError("not read here")

    async def skill(self) -> Skill:
        raise AssertionError("not read here")

    async def skill_zip(self, base_url: str) -> SkillZip:
        raise AssertionError("not read here")

    async def architecture_diagram(self, slug: str) -> ArchitectureDiagram:
        raise AssertionError("not read here")


async def test_the_cache_reads_the_fleet_once_per_ttl_and_one_server_every_time() -> None:
    inner = CountingInventory()
    cached = CachedServerInventory(inner, TtlCache(), ttl=30)
    assert await cached.rows() == [PARSED]
    assert await cached.rows() == [PARSED]
    await cached.server(SERVER_ID)
    await cached.server(SERVER_ID)
    assert (inner.row_reads, inner.server_reads) == (1, 2)


async def test_a_failed_fleet_read_is_not_cached() -> None:
    inner = CountingInventory()
    inner.fail = True
    cached = CachedServerInventory(inner, TtlCache(), ttl=30)
    with pytest.raises(ServerScanUnavailableError):
        await cached.rows()
    inner.fail = False
    assert await cached.rows() == [PARSED]


async def test_the_sites_are_cached_for_their_own_ttl_apart_from_the_rows() -> None:
    clock = [0.0]
    inner = CountingInventory()
    cached = CachedServerInventory(inner, TtlCache(clock=lambda: clock[0]), ttl=30, sites_ttl=10)
    first = await cached.sites()
    assert await cached.sites() == first
    await cached.rows()
    assert (inner.site_reads, inner.row_reads) == (1, 1)
    clock[0] = 11.0
    await cached.sites()
    await cached.rows()
    assert (inner.site_reads, inner.row_reads) == (2, 1)


async def test_without_a_sites_ttl_the_sites_keep_the_rows_ttl() -> None:
    clock = [0.0]
    inner = CountingInventory()
    cached = CachedServerInventory(inner, TtlCache(clock=lambda: clock[0]), ttl=30)
    await cached.sites()
    clock[0] = 29.0
    await cached.sites()
    assert inner.site_reads == 1


async def test_a_failed_sites_read_is_not_cached() -> None:
    inner = CountingInventory()
    inner.fail = True
    cached = CachedServerInventory(inner, TtlCache(), ttl=30, sites_ttl=10)
    with pytest.raises(ServerScanUnavailableError):
        await cached.sites()
    inner.fail = False
    assert (await cached.sites()).sites[0].site_id == "bat-yam"
    assert inner.site_reads == 2
