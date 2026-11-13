"""``GET /api/day1/server-scan/servers`` (docs/notes/2026-11-13-server-scan-area-api.md §8.3).

The fleet as server-scan's rows, admins only, from the one cached read, with
day1's own weak ETag and a bodiless 304 for a current copy. Built on the fake
fleet of ``dev/fleet-fixtures/servers.yaml``.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import ServerScanDeniedError
from wingman_day1.domain.server_scan_servers import FleetRows
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import (
    FakeServerInventory,
    default_fleet_file,
    load_fleet,
)
from wingman_day1.ports import ServerInventory

Auth = Callable[[User], dict[str, str]]
SERVERS = "/api/day1/server-scan/servers"
ROW_FIELDS = {
    "id",
    "name",
    "vendor",
    "model",
    "site_id",
    "source_provider",
    "installation_type",
    "health",
    "maintenance",
    "reservation",
    "openshift_state",
    "cluster_name",
    "mce_name",
    "openshift_reported_name",
    "contested_with",
    "profile_template_name",
    "last_seen_at",
    "stale",
    "reachable",
    "serial",
    "bmc_host",
    "macs",
}


def client(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    inventory: ServerInventory | None,
    **settings: object,
) -> httpx.AsyncClient:
    app = support.build_app(
        gitlab=gitlab,
        hub=None,
        identity=None,
        day2=FakeDay2Addons(),
        clock=clock,
        inventory=inventory,
        **settings,
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://day1.test")


def fleet() -> FakeServerInventory:
    rows, _ = load_fleet(default_fleet_file())
    return FakeServerInventory(rows)


class CountingFleet(FakeServerInventory):
    """The fake fleet, counting how often day1 reads it."""

    def __init__(self) -> None:
        rows, _ = load_fleet(default_fleet_file())
        super().__init__(rows)
        self.reads = 0

    async def fleet(self) -> FleetRows:
        self.reads += 1
        return await super().fleet()


class DeniedFleet(FakeServerInventory):
    async def fleet(self) -> FleetRows:
        raise ServerScanDeniedError(
            "server-scan refused Wingman's token (401): check SERVER_SCAN_TOKEN"
        )


async def test_only_admins_read_the_servers(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        assert (await http.get(SERVERS)).status_code == 401
        viewer = await http.get(SERVERS, headers=auth(support.VIEWER))
        assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")
        assert (await http.get(SERVERS, headers=auth(support.ALICE))).status_code == 200


async def test_every_row_has_server_scans_shape_and_order(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        body = (await http.get(SERVERS, headers=auth(support.ALICE))).json()
    assert set(body) == {"items", "generated_at"}
    rows, _ = load_fleet(default_fleet_file())
    assert [item["name"] for item in body["items"]] == sorted(row.name for row in rows)
    assert all(set(item) == ROW_FIELDS for item in body["items"])
    first = body["items"][0]
    assert set(first["maintenance"]) == {"enabled", "reason", "created_by"}
    assert set(first["reservation"]) == {"held", "holder", "mce_cluster", "infra_env", "expires_at"}
    assert body["generated_at"] is not None


async def test_the_fixtures_maintenance_reservation_and_claims_come_through(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        items = (await http.get(SERVERS, headers=auth(support.ALICE))).json()["items"]
    in_maintenance = [item for item in items if item["maintenance"]["enabled"]]
    assert in_maintenance, "the fixture has a server in maintenance"
    assert all(item["maintenance"]["reason"] for item in in_maintenance)
    assert all(item["reservation"]["held"] is False for item in items)
    assert all(set(item["reservation"].values()) == {False, None} for item in items)
    assert {item["source_provider"] for item in items} >= {"OPENMANAGE"}
    assert all(item["bmc_host"] for item in items)


async def test_an_unchanged_fleet_is_a_bodiless_304(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        first = await http.get(SERVERS, headers=auth(support.ALICE))
        etag = first.headers["etag"]
        assert etag.startswith('W/"')
        assert first.headers["cache-control"] == "no-cache"
        again = await http.get(SERVERS, headers={**auth(support.ALICE), "If-None-Match": etag})
        assert (again.status_code, again.content) == (304, b"")
        assert again.headers["etag"] == etag
        stale = await http.get(SERVERS, headers={**auth(support.ALICE), "If-None-Match": 'W/"old"'})
        assert stale.status_code == 200
        assert stale.json() == first.json()


async def test_a_changed_fleet_has_a_new_etag(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    async with client(support, gitlab, clock, inventory, day1_cache_ttl_seconds=0.01) as http:
        first = await http.get(SERVERS, headers=auth(support.ALICE))
        inventory.replace(dataclasses.replace(inventory.snapshot()[0], health="CRITICAL"))
        await asyncio.sleep(0.02)
        second = await http.get(
            SERVERS, headers={**auth(support.ALICE), "If-None-Match": first.headers["etag"]}
        )
    assert second.status_code == 200
    assert second.headers["etag"] != first.headers["etag"]
    assert second.json()["items"][0]["health"] == "CRITICAL"


async def test_open_pages_share_one_read_of_server_scan(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = CountingFleet()
    async with client(support, gitlab, clock, inventory) as http:
        for _ in range(5):
            assert (await http.get(SERVERS, headers=auth(support.ALICE))).status_code == 200
    assert inventory.reads == 1


async def test_without_server_scan_the_page_is_off(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, None) as http:
        response = await http.get(SERVERS, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
    assert "SERVER_SCAN_URL" in response.json()["detail"]


@pytest.mark.parametrize(
    ("inventory", "detail"),
    [
        (FakeServerInventory(unavailable=True), "unreachable"),
        (DeniedFleet(), "SERVER_SCAN_TOKEN"),
    ],
)
async def test_server_scan_failing_or_refusing_is_502(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    auth: Auth,
    inventory: ServerInventory,
    detail: str,
) -> None:
    async with client(support, gitlab, clock, inventory) as http:
        response = await http.get(SERVERS, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    assert detail in response.json()["detail"]
