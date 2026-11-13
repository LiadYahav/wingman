"""server-scan's ``GET /api/v1/sites`` through HttpServerInventory, and the fake's counts.

The answers are in server-scan's shape (``backend/app/api/v1/sites_schemas.py``
at 92146d3; ADR-0048); the fake is held to server-scan's counting rules (``_pivot`` in
``backend/app/api/v1/sites.py``).
"""

from __future__ import annotations

import copy
import dataclasses
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import ServerScanDeniedError, ServerScanUnavailableError
from wingman_day1.domain.server_scan_sites import Breakdown, FleetSites, VendorCount
from wingman_day1.domain.servers import ServerRow
from wingman_day1.infrastructure.fake_fleet import (
    FakeServerInventory,
    default_fleet_file,
    load_fleet,
)
from wingman_day1.infrastructure.fake_server_scan_sites import count_sites, load_site_catalog
from wingman_day1.infrastructure.server_scan import HttpServerInventory

TOKEN = "server-scan-viewer-token-never-shown-0002"
VENDORS = ("dell", "cisco", "hp", "standalone", "kubevirt")
HEALTH = ("UNKNOWN", "HEALTHY", "WARNING", "MAJOR", "CRITICAL")
TYPES = ("HOSTED_CLUSTER", "MCE", "UPI", "UNCLASSIFIED")
STATES = ("AVAILABLE", "INSTALLED", "INSTALLED_TO_INVENTORY")


def breakdown(
    total: int = 0, *, dell: int = 0, critical: int = 0, maint: int = 0
) -> dict[str, Any]:
    """One server-scan breakdown: ``dell`` Dell servers, the rest healthy unless ``critical``."""
    by_vendor = [{"vendor": v, "count": dell if v == "dell" else 0} for v in VENDORS]
    by_health = dict.fromkeys(HEALTH, 0) | {"HEALTHY": total - critical, "CRITICAL": critical}
    return {
        "total": total,
        "by_vendor": by_vendor,
        "by_health": by_health,
        "in_maintenance": maint,
    }


def sliced(total: int = 0, **counts: int) -> dict[str, Any]:
    """A breakdown with its slices: every server hosted-cluster and installed."""
    return breakdown(total, **counts) | {
        "by_installation_type": {
            t: breakdown(total if t == "HOSTED_CLUSTER" else 0) for t in TYPES
        },
        "by_openshift_state": {s: breakdown(total if s == "INSTALLED" else 0) for s in STATES},
    }


# As server-scan answers it: every configured site in order, an empty one, then unassigned.
ANSWER: dict[str, Any] = {
    "items": [
        {"site_id": "tlv", "name": "Tel Aviv"} | sliced(3, dell=3, critical=1, maint=1),
        {"site_id": "nyc", "name": "New York City"} | sliced(0),
        {"site_id": "unassigned", "name": "Unassigned"} | sliced(1),
    ],
    "fleet": sliced(4, dell=3, critical=1, maint=1),
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


def reply(status: int, body: object = None) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


# ── The real adapter ──────────────────────────────────────────────────────────


async def test_the_sites_are_read_with_the_viewer_token_and_typed() -> None:
    inventory, requests = make(reply(200, ANSWER))
    sites = await inventory.sites()
    (request,) = requests
    assert request.url.path == "/api/v1/sites"
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert [(s.site_id, s.name, s.total) for s in sites.sites] == [
        ("tlv", "Tel Aviv", 3),
        ("nyc", "New York City", 0),
        ("unassigned", "Unassigned", 1),
    ]
    tlv = sites.sites[0]
    assert tlv.by_vendor[0] == VendorCount(vendor="dell", count=3)
    assert [v.vendor for v in tlv.by_vendor] == list(VENDORS)
    assert (tlv.by_health["CRITICAL"], tlv.in_maintenance) == (1, 1)
    assert list(tlv.by_installation_type) == list(TYPES)
    assert list(tlv.by_openshift_state) == list(STATES)
    assert tlv.by_installation_type["HOSTED_CLUSTER"].total == 3
    assert (sites.fleet.total, sites.fleet.by_openshift_state["INSTALLED"].total) == (4, 4)


async def test_without_a_token_no_authorization_header_is_sent() -> None:
    inventory, requests = make(reply(200, ANSWER), token="")
    await inventory.sites()
    assert "Authorization" not in requests[0].headers


async def test_keys_server_scan_adds_later_are_kept_in_its_order() -> None:
    answer = copy.deepcopy(ANSWER)
    fleet = answer["fleet"]
    fleet["by_vendor"].append({"vendor": "supermicro", "count": 0})
    fleet["by_health"] = {"INFO": 0, **fleet["by_health"]}
    fleet["by_installation_type"]["HUB"] = breakdown()
    fleet["by_openshift_state"]["RETIRED"] = breakdown()
    inventory, _ = make(reply(200, answer))
    sites = await inventory.sites()
    assert [v.vendor for v in sites.fleet.by_vendor][-1] == "supermicro"
    assert list(sites.fleet.by_health) == ["INFO", *HEALTH]
    assert list(sites.fleet.by_installation_type) == [*TYPES, "HUB"]
    assert list(sites.fleet.by_openshift_state) == [*STATES, "RETIRED"]


def broken(change: Callable[[dict[str, Any]], object]) -> dict[str, Any]:
    answer = copy.deepcopy(ANSWER)
    change(answer)
    return answer


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"items": []},
        {"fleet": ANSWER["fleet"]},
        broken(lambda a: a.update(items={})),
        broken(lambda a: a["items"][0].pop("site_id")),
        broken(lambda a: a["items"][0].update(name="")),
        broken(lambda a: a["items"][0].update(total="3")),
        broken(lambda a: a["items"][0].update(total=True)),
        broken(lambda a: a["items"][0].update(total=-1)),
        broken(lambda a: a["items"][0].update(total=2.5)),
        broken(lambda a: a["items"][0].update(by_vendor={})),
        broken(lambda a: a["items"][0]["by_vendor"].append({"vendor": "dell"})),
        broken(lambda a: a["items"][0].update(by_health=[])),
        broken(lambda a: a["items"][0]["by_health"].update(HEALTHY=None)),
        broken(lambda a: a["items"][0].pop("by_openshift_state")),
        broken(lambda a: a["items"][0]["by_installation_type"].update(UPI=[])),
        broken(lambda a: a["fleet"].pop("in_maintenance")),
    ],
)
async def test_malformed_sites_are_unavailable_never_zero(body: object) -> None:
    inventory, _ = make(reply(200, body))
    with pytest.raises(ServerScanUnavailableError, match="malformed sites"):
        await inventory.sites()


async def test_a_body_that_is_not_json_is_unavailable() -> None:
    inventory, _ = make(lambda _r: httpx.Response(200, text="<html>proxy</html>"))
    with pytest.raises(ServerScanUnavailableError, match="malformed sites"):
        await inventory.sites()


@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_token_is_denied_and_names_the_setting(status: int) -> None:
    inventory, _ = make(reply(status, {"detail": "no"}))
    with pytest.raises(ServerScanDeniedError, match="SERVER_SCAN_TOKEN"):
        await inventory.sites()


@pytest.mark.parametrize("status", [404, 500, 503])
async def test_any_other_answer_is_unavailable(status: int) -> None:
    inventory, _ = make(reply(status, {}))
    with pytest.raises(ServerScanUnavailableError, match=f"answered {status} listing sites"):
        await inventory.sites()


@pytest.mark.parametrize("exc", [httpx.ConnectError, httpx.ReadTimeout])
async def test_transport_failures_are_unavailable(exc: type[httpx.TransportError]) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exc("boom", request=request)

    inventory, _ = make(fail)
    with pytest.raises(ServerScanUnavailableError, match="unreachable listing sites"):
        await inventory.sites()


async def test_the_sites_read_is_counted_as_list_sites() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    ok, _ = make(reply(200, ANSWER), metrics=metrics)
    await ok.sites()
    denied, _ = make(reply(403, {}), metrics=metrics)
    with pytest.raises(ServerScanDeniedError):
        await denied.sites()
    malformed, _ = make(reply(200, {}), metrics=metrics)
    with pytest.raises(ServerScanUnavailableError):
        await malformed.sites()

    def count(outcome: str) -> float | None:
        labels = {"dependency": "server_scan", "operation": "list_sites", "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert (count("ok"), count("denied"), count("unavailable")) == (1, 1, 1)


# ── The fake: server-scan's counting rules ────────────────────────────────────


def row(name: str, **fields: Any) -> ServerRow:
    base: dict[str, Any] = {
        "id": f"srv_{name}",
        "name": name,
        "state": "INSTALLED",
        "health": "HEALTHY",
        "vendor": "dell",
        "site": "tlv",
        "installation_type": "HOSTED_CLUSTER",
    }
    return ServerRow(**(base | fields))


CATALOG = [("tlv", "Tel Aviv"), ("nyc", "New York City"), ("bat-yam", "Bat Yam")]


def counts(b: Breakdown) -> tuple[int, dict[str, int], dict[str, int], int]:
    """A breakdown as (total, nonzero vendors, nonzero health, in maintenance)."""
    vendors = {v.vendor: v.count for v in b.by_vendor if v.count}
    health = {h: n for h, n in b.by_health.items() if n}
    return b.total, vendors, health, b.in_maintenance


def by_site(sites: FleetSites) -> dict[str, Any]:
    return {s.site_id: s for s in sites.sites}


def test_every_configured_site_in_order_an_empty_one_at_zero_and_unassigned_last() -> None:
    sites = count_sites([row("a"), row("b", site="nyc")], CATALOG)
    assert [(s.site_id, s.name, s.total) for s in sites.sites] == [
        ("tlv", "Tel Aviv", 1),
        ("nyc", "New York City", 1),
        ("bat-yam", "Bat Yam", 0),
        ("unassigned", "Unassigned", 0),
    ]
    empty = by_site(sites)["bat-yam"]
    assert [v.vendor for v in empty.by_vendor] == list(VENDORS)
    assert empty.by_health == dict.fromkeys(HEALTH, 0)
    assert list(empty.by_installation_type) == list(TYPES)
    assert list(empty.by_openshift_state) == list(STATES)


def test_a_server_with_no_site_or_one_no_longer_configured_is_unassigned() -> None:
    sites = count_sites([row("a", site=None), row("b", site="haifa"), row("c")], CATALOG)
    assert by_site(sites)["unassigned"].total == 2
    assert sites.fleet.total == 3


def test_health_maintenance_vendor_type_and_state_are_counted_with_their_fallbacks() -> None:
    rows = [
        row("a", health="CRITICAL", maintenance=True),
        row("b", health="SOMETHING_NEW", vendor="cisco"),
        row("c", vendor="supermicro", installation_type=None, state="AVAILABLE"),
        row("d", installation_type="UPI", state="RETIRED"),
        row("e", installation_type="MCE", state="INSTALLED_TO_INVENTORY", vendor=None),
    ]
    tlv = by_site(count_sites(rows, CATALOG))["tlv"]
    # An unknown vendor is counted in the total, in no vendor entry
    assert counts(tlv) == (
        5,
        {"dell": 2, "cisco": 1},
        {"CRITICAL": 1, "UNKNOWN": 1, "HEALTHY": 3},
        1,
    )
    assert {t: b.total for t, b in tlv.by_installation_type.items()} == {
        "HOSTED_CLUSTER": 2,
        "MCE": 1,
        "UPI": 1,
        "UNCLASSIFIED": 1,
    }
    assert {s: b.total for s, b in tlv.by_openshift_state.items()} == {
        "AVAILABLE": 2,
        "INSTALLED": 2,
        "INSTALLED_TO_INVENTORY": 1,
    }
    assert counts(tlv.by_installation_type["HOSTED_CLUSTER"]) == (
        2,
        {"dell": 1, "cisco": 1},
        {"CRITICAL": 1, "UNKNOWN": 1},
        1,
    )


def test_the_fleet_is_every_site_summed_and_its_slices_add_up() -> None:
    rows = [row("a"), row("b", site="nyc", installation_type="UPI"), row("c", site=None)]
    sites = count_sites(rows, CATALOG)
    fleet = sites.fleet
    assert fleet.total == sum(s.total for s in sites.sites) == 3
    assert sum(b.total for b in fleet.by_installation_type.values()) == 3
    assert sum(b.total for b in fleet.by_openshift_state.values()) == 3
    assert fleet.by_installation_type["UPI"].total == 1


async def test_a_fake_without_a_catalog_lists_its_rows_sites_named_like_server_scan() -> None:
    fake = FakeServerInventory([row("a", site="tlv"), row("b", site="bat-yam")])
    sites = await fake.sites()
    assert [(s.site_id, s.name, s.total) for s in sites.sites] == [
        ("bat-yam", "Bat Yam", 1),
        ("tlv", "Tlv", 1),
        ("unassigned", "Unassigned", 0),
    ]


async def test_the_fake_counts_its_rows_as_they_are_now_and_fails_when_down() -> None:
    fake = FakeServerInventory([row("a", site="tlv"), row("b", site="bat-yam")], sites=CATALOG)
    assert (await fake.sites()).fleet.by_openshift_state["AVAILABLE"].total == 0
    freed = dataclasses.replace(row("a", site="tlv"), state="AVAILABLE")
    fake.replace(freed)
    assert (await fake.sites()).fleet.by_openshift_state["AVAILABLE"].total == 1
    fake.unavailable = True
    with pytest.raises(ServerScanUnavailableError):
        await fake.sites()


async def test_the_fake_fleet_counts_over_its_fixture_catalog() -> None:
    rows, _ = load_fleet(default_fleet_file())
    catalog = load_site_catalog(default_fleet_file())
    assert catalog == (("site1", "Site 1"), ("site2", "Site 2"), ("site3", "Site 3"))
    sites = await FakeServerInventory(rows, sites=catalog).sites()
    assert [s.site_id for s in sites.sites] == ["site1", "site2", "site3", "unassigned"]
    totals = {s.site_id: s.total for s in sites.sites}
    assert totals["site3"] == 0
    assert sites.fleet.total == len(rows) == sum(totals.values())
