"""``/api/day1/server-scan/servers`` (docs/notes/2026-11-13-server-scan-area-api.md §8).

The fleet as server-scan's rows, admins only, from the one cached read, with
day1's own weak ETag and a bodiless 304 for a current copy; and a server's
maintenance on and off: allowed, refused, unanswered, and without the admin
token. Built on the fake fleet of ``dev/fleet-fixtures/servers.yaml``.
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
from wingman_day1.domain.errors import AmbiguousServerScanWriteError, ServerScanDeniedError
from wingman_day1.domain.server_scan_servers import FleetRows, MaintenanceStart, ServerMaintenance
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
    assert set(body) == {"items", "generated_at", "maintenance_available", "maintenance_detail"}
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


# ── The maintenance toggle (§8.5) ────────────────────────────────────────────


def maintenance(server_id: str) -> str:
    return f"{SERVERS}/{server_id}/maintenance"


class UnansweredFleet(FakeServerInventory):
    """server-scan taking a write and never answering."""

    async def start_maintenance(self, server_id: str, start: MaintenanceStart) -> ServerMaintenance:
        raise AmbiguousServerScanWriteError(
            "starting maintenance was sent to server-scan but no answer came back: it may have "
            "changed. Reload the servers and look at its row before trying again."
        )


async def test_an_admin_puts_a_server_into_maintenance_and_ends_it(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    server = next(row for row in inventory.snapshot() if not row.maintenance)
    admin = auth(support.ALICE)
    body = {"reason": "Replacing PSU 2 — INC-4417", "expected_end": "2026-11-14T16:00:00Z"}
    async with client(support, gitlab, clock, inventory) as http:
        before = await http.get(SERVERS, headers=admin)
        started = await http.put(maintenance(server.id), json=body, headers=admin)
        assert started.status_code == 200
        assert started.json() == {
            "id": server.id,
            "name": server.name,
            "maintenance": {"enabled": True, "reason": body["reason"], "created_by": "dev"},
        }
        after = await http.get(SERVERS, headers={**admin, "If-None-Match": before.headers["etag"]})
        assert after.status_code == 200, "day1 forgets its cached rows after a write"
        row = next(item for item in after.json()["items"] if item["id"] == server.id)
        assert row["maintenance"]["enabled"] is True
        ended = await http.delete(maintenance(server.id), headers=admin)
    assert ended.json()["maintenance"] == {"enabled": False, "reason": None, "created_by": None}
    ((_, start),) = inventory.maintenance_starts
    assert start.expected_end is not None and start.expected_end.hour == 16


async def test_a_blank_reason_is_sent_as_none(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    server = inventory.snapshot()[0]
    async with client(support, gitlab, clock, inventory) as http:
        response = await http.put(
            maintenance(server.id), json={"reason": "  "}, headers=auth(support.ALICE)
        )
    assert response.status_code == 200
    assert inventory.maintenance_starts == [(server.id, MaintenanceStart())]


async def test_only_admins_change_maintenance(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    server = inventory.snapshot()[0]
    async with client(support, gitlab, clock, inventory) as http:
        assert (await http.put(maintenance(server.id), json={})).status_code == 401
        viewer = await http.put(maintenance(server.id), json={}, headers=auth(support.VIEWER))
        assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")
        viewer_end = await http.delete(maintenance(server.id), headers=auth(support.VIEWER))
        assert viewer_end.status_code == 403
    assert inventory.maintenance_starts == []


@pytest.mark.parametrize(
    "body",
    [{"reason": "x" * 501}, {"expected_end": "tomorrow"}, {"expected_end": "2026-11-14T16:00:00"}],
)
async def test_a_reason_too_long_or_an_end_that_is_no_instant_is_refused(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, body: dict[str, str]
) -> None:
    inventory = fleet()
    async with client(support, gitlab, clock, inventory) as http:
        response = await http.put(
            maintenance(inventory.snapshot()[0].id), json=body, headers=auth(support.ALICE)
        )
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert inventory.maintenance_starts == []


async def test_an_unknown_server_is_not_found(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        response = await http.delete(maintenance("srv_unknown"), headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")


async def test_an_unanswered_write_is_ambiguous_never_retried(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    rows, _ = load_fleet(default_fleet_file())
    async with client(support, gitlab, clock, UnansweredFleet(rows)) as http:
        response = await http.put(maintenance(rows[0].id), json={}, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (504, "AMBIGUOUS_WRITE")
    assert "before trying again" in response.json()["detail"]


@pytest.mark.parametrize(
    ("tokens", "available"),
    [
        ({}, True),
        ({"server_scan_token": "viewer", "server_scan_admin_token": "admin"}, True),
        ({"server_scan_admin_token": "admin"}, True),
        ({"server_scan_token": "viewer"}, False),
    ],
)
async def test_the_toggle_needs_the_admin_token_unless_server_scan_runs_with_auth_off(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    auth: Auth,
    tokens: dict[str, str],
    available: bool,
) -> None:
    inventory = fleet()
    server = inventory.snapshot()[0]
    async with client(support, gitlab, clock, inventory, **tokens) as http:
        body = (await http.get(SERVERS, headers=auth(support.ALICE))).json()
        write = await http.put(maintenance(server.id), json={}, headers=auth(support.ALICE))
    assert body["maintenance_available"] is available
    if available:
        assert (body["maintenance_detail"], write.status_code) == (None, 200)
    else:
        assert "SERVER_SCAN_ADMIN_TOKEN" in body["maintenance_detail"]
        assert (write.status_code, write.json()["code"]) == (501, "FEATURE_DISABLED")
        assert write.json()["detail"] == body["maintenance_detail"]
        assert inventory.maintenance_starts == []


async def test_without_server_scan_the_writes_are_off(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, None) as http:
        response = await http.delete(maintenance("srv_1"), headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
