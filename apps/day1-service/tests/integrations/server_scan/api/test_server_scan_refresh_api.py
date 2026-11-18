"""Fetch now's route (docs/notes/2026-11-13-server-scan-area-api.md §9.9).

``POST /api/day1/server-scan/servers/{id}/refresh``: admins only, as
server-scan keeps it; the server's record as just read, with the
deployment's switches; server-scan's refusals as ``409
SERVER_REFRESH_REFUSED`` in its words; 404, 501 without the admin token beside
a viewer token, 502 when server-scan fails, 504 when unanswered, never
retried; logged with the person. Built on the fake fleet.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import AmbiguousServerScanWriteError, ServerScanUnavailableError
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import load_fleet
from wingman_day1.integrations.server_scan.domain.record import ServerRecord
from wingman_day1.integrations.server_scan.domain.servers import REFRESH_OFF
from wingman_day1.integrations.server_scan.infrastructure.fakes.inventory import (
    FakeServerInventory,
    default_fleet_file,
)
from wingman_day1.integrations.server_scan.infrastructure.fakes.records import (
    default_records_file,
    load_records,
)
from wingman_day1.integrations.server_scan.ports import ServerInventory

Auth = Callable[[User], dict[str, str]]
SERVERS = "/api/day1/server-scan/servers"


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


def refresh(server_id: str) -> str:
    return f"{SERVERS}/{server_id}/refresh"


def by_provider(inventory: FakeServerInventory, provider: str) -> str:
    return next(row.id for row in inventory.snapshot() if row.source_provider == provider)


class UnansweredFleet(FakeServerInventory):
    async def refresh(self, server_id: str) -> ServerRecord:
        self.refreshes.append(server_id)
        raise AmbiguousServerScanWriteError("sent, no answer came back (fake)")


class FailingFleet(FakeServerInventory):
    async def refresh(self, server_id: str) -> ServerRecord:
        raise ServerScanUnavailableError(
            "server-scan could not finish reading it from its vendor manager: timeout (fake)"
        )


async def test_only_admins_fetch_a_server(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    path = refresh(by_provider(inventory, "OPENMANAGE"))
    async with client(support, gitlab, clock, inventory) as http:
        assert (await http.post(path)).status_code == 401
        viewer = await http.post(path, headers=auth(support.VIEWER))
        assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")
    assert inventory.refreshes == []


async def test_an_admin_fetches_a_server_and_gets_its_record_with_the_switches(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    server_id = by_provider(inventory, "OPENMANAGE")
    async with client(support, gitlab, clock, inventory) as http:
        before = (await http.get(f"{SERVERS}/{server_id}", headers=auth(support.ALICE))).json()
        response = await http.post(refresh(server_id), headers=auth(support.ALICE))
        rows = (await http.get(SERVERS, headers=auth(support.ALICE))).json()["items"]
    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(before)
    assert (body["id"], body["revision"]) == (server_id, before["revision"])
    assert (body["refresh_available"], body["refresh_detail"]) == (True, None)
    assert body["last_seen_at"] != before["last_seen_at"]
    row = next(item for item in rows if item["id"] == server_id)
    assert row["last_seen_at"] == body["last_seen_at"], "the rows are read again after it"
    assert inventory.refreshes == [server_id]


async def test_what_server_scan_cannot_read_is_409_in_its_words(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    row = next(row for row in inventory.snapshot() if row.source_provider == "OPENMANAGE")
    inventory.replace(dataclasses.replace(row, source_provider="REDFISH_STANDALONE"))
    server_id = row.id
    async with client(support, gitlab, clock, inventory) as http:
        response = await http.post(refresh(server_id), headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (409, "SERVER_REFRESH_REFUSED")
    assert "run its collector job instead" in response.json()["detail"]


async def test_an_unknown_server_is_404(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        response = await http.post(refresh("srv_unknown"), headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")


async def test_an_unanswered_fetch_is_504_never_retried(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    rows, _ = load_fleet(default_fleet_file())
    inventory = UnansweredFleet(rows)
    async with client(support, gitlab, clock, inventory) as http:
        response = await http.post(refresh(rows[0].id), headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (504, "AMBIGUOUS_WRITE")
    assert inventory.refreshes == [rows[0].id]


async def test_a_manager_failing_is_502_in_server_scans_words(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    rows, _ = load_fleet(default_fleet_file())
    async with client(support, gitlab, clock, FailingFleet(rows)) as http:
        response = await http.post(refresh(rows[0].id), headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    assert "vendor manager: timeout" in response.json()["detail"]


@pytest.mark.parametrize(
    ("tokens", "available"),
    [
        ({}, True),
        ({"server_scan_token": "viewer", "server_scan_admin_token": "admin"}, True),
        ({"server_scan_admin_token": "admin"}, True),
        ({"server_scan_token": "viewer"}, False),
    ],
)
async def test_fetch_now_needs_the_admin_token_unless_server_scan_runs_with_auth_off(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    auth: Auth,
    tokens: dict[str, str],
    available: bool,
) -> None:
    inventory = fleet()
    server_id = by_provider(inventory, "OPENMANAGE")
    async with client(support, gitlab, clock, inventory, **tokens) as http:
        rows = (await http.get(SERVERS, headers=auth(support.ALICE))).json()
        record = (await http.get(f"{SERVERS}/{server_id}", headers=auth(support.ALICE))).json()
        write = await http.post(refresh(server_id), headers=auth(support.ALICE))
    assert rows["refresh_available"] is record["refresh_available"] is available
    if available:
        assert (rows["refresh_detail"], write.status_code) == (None, 200)
    else:
        assert rows["refresh_detail"] == record["refresh_detail"] == REFRESH_OFF
        assert (write.status_code, write.json()["code"]) == (501, "FEATURE_DISABLED")
        assert write.json()["details"]["setting"] == "SERVER_SCAN_ADMIN_TOKEN"
        assert inventory.refreshes == []


async def test_without_server_scan_fetch_now_is_501(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, None) as http:
        response = await http.post(refresh("srv_1"), headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")


async def test_a_fetch_is_logged_with_the_person(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, caplog: pytest.LogCaptureFixture
) -> None:
    inventory = fleet()
    server_id = by_provider(inventory, "OPENMANAGE")
    async with client(support, gitlab, clock, inventory) as http:
        with caplog.at_level(logging.INFO, logger="wingman_day1.application.server_scan"):
            await http.post(refresh(server_id), headers=auth(support.ALICE))
    (line,) = [r for r in caplog.records if r.__dict__.get("event") == "server_refreshed"]
    assert (line.__dict__["user"], line.__dict__["server_id"]) == (
        support.ALICE.username,
        server_id,
    )
