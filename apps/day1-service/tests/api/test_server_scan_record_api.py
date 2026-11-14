"""A server's page's routes (docs/notes/2026-11-13-server-scan-area-api.md §9).

The record in server-scan's shape with the deployment's two switches, a VM's
host, and History with the auditor token: admins only, 404, 501 when off or
without the auditor token, 502 when server-scan fails or refuses, 422 for an
out-of-range page. Built on the fake fleet and its records fixture.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import ServerScanDeniedError
from wingman_day1.domain.server_scan_events import EventPage
from wingman_day1.domain.server_scan_record import HISTORY_OFF, ServerRecord
from wingman_day1.domain.server_scan_servers import MAINTENANCE_OFF
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import (
    FakeServerInventory,
    default_fleet_file,
    load_fleet,
)
from wingman_day1.infrastructure.fake_server_records import default_records_file, load_records
from wingman_day1.ports import ServerInventory

Auth = Callable[[User], dict[str, str]]
SERVERS = "/api/day1/server-scan/servers"
RECORD_FIELDS = {
    "id",
    "name",
    "model",
    "profile_template",
    "identity",
    "hardware",
    "network",
    "connectivity",
    "classification",
    "health",
    "maintenance",
    "reservation",
    "site_id",
    "manager_id",
    "source_provider",
    "openshift",
    "vm_host",
    "unread_fields",
    "nic_os_names",
    "tags",
    "last_seen_at",
    "stale",
    "reachable",
    "unreachable_since",
    "unreachable_reason",
    "updated_at",
    "created_at",
    "maintenance_available",
    "maintenance_detail",
    "history_available",
    "history_detail",
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
    return FakeServerInventory(rows, records=load_records(default_records_file()))


def first_id(inventory: FakeServerInventory) -> str:
    return inventory.snapshot()[0].id


class DeniedFleet(FakeServerInventory):
    async def record(self, server_id: str) -> ServerRecord:
        raise ServerScanDeniedError(
            "server-scan refused Wingman's token (401): check SERVER_SCAN_TOKEN"
        )

    async def server_events(
        self, server_id: str, *, cursor: str | None, page_size: int
    ) -> EventPage:
        raise ServerScanDeniedError(
            "server-scan refused Wingman's auditor token (403): check SERVER_SCAN_AUDITOR_TOKEN"
        )


async def test_only_admins_read_a_server(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    server = f"{SERVERS}/{first_id(inventory)}"
    async with client(support, gitlab, clock, inventory) as http:
        for path in (server, f"{server}/vm-host", f"{server}/events"):
            assert (await http.get(path)).status_code == 401
            viewer = await http.get(path, headers=auth(support.VIEWER))
            assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")


async def test_the_record_is_server_scans_shape_with_the_two_switches(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    row = inventory.snapshot()[0]
    async with client(support, gitlab, clock, inventory) as http:
        response = await http.get(f"{SERVERS}/{row.id}", headers=auth(support.ALICE))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == RECORD_FIELDS
    assert (body["id"], body["name"], body["identity"]["serial"]) == (row.id, row.name, row.serial)
    assert set(body["reservation"]) >= {"held", "holder", "mce_cluster", "infra_env", "expires_at"}
    assert set(body["maintenance"]) >= {"enabled", "reason", "created_by", "expected_end"}
    assert body["hardware"]["cpu"]["threads"] > 0
    assert (body["maintenance_available"], body["history_available"]) == (True, True)
    assert (body["maintenance_detail"], body["history_detail"]) == (None, None)


async def test_an_unknown_server_is_404(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        response = await http.get(f"{SERVERS}/srv_unknown", headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")


async def test_a_physical_server_has_no_vm_host(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    async with client(support, gitlab, clock, inventory) as http:
        path = f"{SERVERS}/{first_id(inventory)}/vm-host"
        response = await http.get(path, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
    assert "not a virtual machine" in response.json()["detail"]


async def test_history_pages_newest_first(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    path = f"{SERVERS}/{first_id(inventory)}/events"
    async with client(support, gitlab, clock, inventory) as http:
        first = (await http.get(path, params={"page_size": 2}, headers=auth(support.ALICE))).json()
        cursor = first["page"]["next_cursor"]
        rest = await http.get(
            path, params={"cursor": cursor, "page_size": 50}, headers=auth(support.ALICE)
        )
    assert set(first) == {"items", "page"}
    assert len(first["items"]) == 2 and first["page"]["has_more"] is True
    assert set(first["items"][0]) == {
        "id",
        "event_type",
        "server_id",
        "server_name",
        "actor",
        "request_id",
        "created_at",
        "data",
    }
    assert rest.json()["items"][-1]["event_type"] == "SERVER_CREATED"


@pytest.mark.parametrize("params", [{"page_size": 0}, {"page_size": 201}, {"cursor": "c" * 513}])
async def test_an_out_of_range_history_page_is_422(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, params: dict[str, str | int]
) -> None:
    inventory = fleet()
    async with client(support, gitlab, clock, inventory) as http:
        path = f"{SERVERS}/{first_id(inventory)}/events"
        response = await http.get(path, params=params, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    ("settings", "available"),
    [
        ({"server_scan_token": "viewer", "server_scan_auditor_token": "auditor"}, True),
        ({"server_scan_auditor_token": "auditor"}, True),
        ({}, True),
        ({"server_scan_token": "viewer"}, False),
    ],
)
async def test_history_needs_the_auditor_token_unless_server_scan_runs_with_auth_off(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    auth: Auth,
    settings: dict[str, str],
    available: bool,
) -> None:
    inventory = fleet()
    server = f"{SERVERS}/{first_id(inventory)}"
    async with client(support, gitlab, clock, inventory, **settings) as http:
        record = (await http.get(server, headers=auth(support.ALICE))).json()
        history = await http.get(f"{server}/events", headers=auth(support.ALICE))
    assert record["history_available"] is available
    if available:
        assert (record["history_detail"], history.status_code) == (None, 200)
    else:
        assert record["history_detail"] == HISTORY_OFF
        assert (history.status_code, history.json()["code"]) == (501, "FEATURE_DISABLED")
        assert "SERVER_SCAN_AUDITOR_TOKEN" in history.json()["detail"]
    viewer_only = "server_scan_token" in settings
    assert record["maintenance_detail"] == (MAINTENANCE_OFF if viewer_only else None)


async def test_without_server_scan_a_server_is_501(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, None) as http:
        response = await http.get(f"{SERVERS}/srv_x", headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
    assert "SERVER_SCAN_URL" in response.json()["detail"]


async def test_a_refused_token_is_502_naming_it(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    rows, _ = load_fleet(default_fleet_file())
    server = f"{SERVERS}/{rows[0].id}"
    async with client(support, gitlab, clock, DeniedFleet(rows)) as http:
        record = await http.get(server, headers=auth(support.ALICE))
        history = await http.get(f"{server}/events", headers=auth(support.ALICE))
    assert (record.status_code, record.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    assert "SERVER_SCAN_TOKEN" in record.json()["detail"]
    assert history.status_code == 502
    assert "SERVER_SCAN_AUDITOR_TOKEN" in history.json()["detail"]
