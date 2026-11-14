"""The Events page's routes (docs/notes/2026-11-13-server-scan-area-api.md §14).

``GET /api/day1/server-scan/events`` and ``/events/actors``: server-scan's
audit trail of the fleet in its shape, filtered and paged as there, with
History's auditor token and guard. Admins only; 422 for a parameter outside
its checks or a cursor server-scan refuses; 501 without server-scan, or
without the auditor token (naming it in ``details.setting``); 502 when
server-scan fails or refuses the token. Built on the fake fleet's trail.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import ServerScanDeniedError, ServerScanUnavailableError
from wingman_day1.domain.server_scan_events import (
    EVENTS_OFF,
    HISTORY_OFF,
    EventActorList,
    EventPage,
    EventQuery,
)
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import (
    FakeServerInventory,
    default_fleet_file,
    load_fleet,
)
from wingman_day1.infrastructure.fake_server_records import default_records_file, load_records
from wingman_day1.infrastructure.fake_server_scan_events import default_events_file, load_events
from wingman_day1.ports import ServerInventory

Auth = Callable[[User], dict[str, str]]
EVENTS = "/api/day1/server-scan/events"
ACTORS = "/api/day1/server-scan/events/actors"
EVENT_FIELDS = {
    "id",
    "event_type",
    "server_id",
    "server_name",
    "actor",
    "request_id",
    "created_at",
    "data",
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
    return FakeServerInventory(
        rows,
        records=load_records(default_records_file()),
        events=load_events(default_events_file(), rows),
    )


class DeniedFleet(FakeServerInventory):
    """server-scan refusing the auditor token."""

    async def events(self, query: EventQuery) -> EventPage:
        raise ServerScanDeniedError(
            "server-scan refused Wingman's auditor token (403) listing events: "
            "check SERVER_SCAN_AUDITOR_TOKEN"
        )

    async def event_actors(self) -> EventActorList:
        raise ServerScanUnavailableError("server-scan answered 500 listing the events' actors")


async def test_only_admins_read_the_audit_trail(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        for path in (EVENTS, ACTORS):
            assert (await http.get(path)).status_code == 401
            viewer = await http.get(path, headers=auth(support.VIEWER))
            assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")


async def test_the_trail_is_server_scans_shape_in_cursor_pages(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        first = (await http.get(EVENTS, headers=auth(support.ALICE))).json()
        cursor = first["page"]["next_cursor"]
        rest = await http.get(EVENTS, params={"cursor": cursor}, headers=auth(support.ALICE))
    assert set(first) == {"items", "page"}
    assert set(first["items"][0]) == EVENT_FIELDS
    assert set(first["items"][0]["actor"]) == {"type", "id", "display"}
    assert (len(first["items"]), first["page"]["has_more"], first["page"]["page_size"]) == (
        50,
        True,
        50,
    )
    total = first["page"]["total"]
    page = rest.json()["page"]
    assert (page["total"], page["has_more"]) == (None, False)
    ids = [e["id"] for e in first["items"] + rest.json()["items"]]
    assert len(ids) == len(set(ids)) == total


async def test_the_filters_are_server_scans(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    params = {
        "event_type": "MAINTENANCE_ENABLED",
        "server_name": "csfake0302",
        "actor_id": "alice",
        "since": "2026-11-10T00:00:00+02:00",
        "until": "2026-11-11T00:00:00Z",
        "page_size": 10,
    }
    async with client(support, gitlab, clock, fleet()) as http:
        response = await http.get(EVENTS, params=params, headers=auth(support.ALICE))
    (event,) = response.json()["items"]
    assert (event["event_type"], event["actor"]["id"], event["created_at"]) == (
        "MAINTENANCE_ENABLED",
        "alice",
        "2026-11-10T10:00:00Z",
    )
    assert event["server_name"] == "ocp-cisco-m6-site1-128c-512gb-CSFAKE0302"


async def test_the_actors_are_server_scans_shape_busiest_first(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        items = (await http.get(ACTORS, headers=auth(support.ALICE))).json()["items"]
    assert set(items[0]) == {"id", "type", "display", "event_count"}
    counts = [item["event_count"] for item in items]
    assert counts == sorted(counts, reverse=True)
    assert {"id": "alice", "type": "USER", "display": "Alice Cohen"}.items() <= next(
        item for item in items if item["id"] == "alice"
    ).items()


@pytest.mark.parametrize(
    "params",
    [
        {"page_size": 0},
        {"page_size": 201},
        {"cursor": "c" * 513},
        {"event_type": "health_changed"},
        {"event_type": "A" * 65},
        {"server_name": ""},
        {"actor_id": "a" * 257},
        {"server_id": ""},
        {"since": "2026-11-01T00:00:00"},
        {"until": "yesterday"},
    ],
)
async def test_a_parameter_outside_its_checks_is_422(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, params: dict[str, str | int]
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        response = await http.get(EVENTS, params=params, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")


async def test_a_cursor_server_scan_refuses_is_422_in_its_words(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        response = await http.get(EVENTS, params={"cursor": "forged"}, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert "Malformed event cursor" in response.json()["detail"]


@pytest.mark.parametrize(
    ("settings", "available"),
    [
        ({"server_scan_token": "viewer", "server_scan_auditor_token": "auditor"}, True),
        ({"server_scan_auditor_token": "auditor"}, True),
        ({}, True),
        ({"server_scan_token": "viewer"}, False),
    ],
)
async def test_events_need_the_auditor_token_unless_server_scan_runs_with_auth_off(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    auth: Auth,
    settings: dict[str, str],
    available: bool,
) -> None:
    async with client(support, gitlab, clock, fleet(), **settings) as http:
        answers = [await http.get(path, headers=auth(support.ALICE)) for path in (EVENTS, ACTORS)]
    for answer in answers:
        if available:
            assert answer.status_code == 200
            continue
        problem = answer.json()
        assert (answer.status_code, problem["code"]) == (501, "FEATURE_DISABLED")
        assert problem["detail"] == EVENTS_OFF
        assert problem["details"]["setting"] == "SERVER_SCAN_AUDITOR_TOKEN"


async def test_historys_501_names_the_auditor_token_too(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    path = f"/api/day1/server-scan/servers/{inventory.snapshot()[0].id}/events"
    async with client(support, gitlab, clock, inventory, server_scan_token="viewer") as http:
        problem = (await http.get(path, headers=auth(support.ALICE))).json()
    assert (problem["detail"], problem["details"]["setting"]) == (
        HISTORY_OFF,
        "SERVER_SCAN_AUDITOR_TOKEN",
    )


async def test_without_server_scan_the_trail_is_501_naming_no_token(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, None) as http:
        for path in (EVENTS, ACTORS):
            problem = (await http.get(path, headers=auth(support.ALICE))).json()
            assert (problem["status"], problem["code"]) == (501, "FEATURE_DISABLED")
            assert "SERVER_SCAN_URL" in problem["detail"]
            assert "setting" not in problem.get("details", {})


async def test_server_scan_refusing_or_failing_is_502(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    rows, _ = load_fleet(default_fleet_file())
    async with client(support, gitlab, clock, DeniedFleet(rows)) as http:
        events = await http.get(EVENTS, headers=auth(support.ALICE))
        actors = await http.get(ACTORS, headers=auth(support.ALICE))
    assert (events.status_code, events.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    assert "SERVER_SCAN_AUDITOR_TOKEN" in events.json()["detail"]
    assert (actors.status_code, actors.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
