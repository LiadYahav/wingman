"""The Events page: the fleet's audit trail and its actors (ADR-0048, 3.31.0).

The adapter against server-scan's answers (MockTransport), in the shape its
``backend/app/api/v1/events_schemas.py`` sends at 92146d3: the filters and
cursor sent as given, the auditor token on both reads only, a refused cursor
or token, malformed answers, the metrics. The use case keeps Events off
without the auditor token, as History; the fake filters and pages its trail
(every server's History and ``events.yaml``) as server-scan does
(docs/notes/2026-11-13-server-scan-area-api.md §14).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.application.server_scan import ServerScanService
from wingman_day1.domain.errors import (
    ServerScanAuditOffError,
    ServerScanDeniedError,
    ServerScanRefusedError,
    ServerScanUnavailableError,
)
from wingman_day1.domain.server_scan_events import EVENTS_OFF, HISTORY_OFF, EventQuery, audit_detail
from wingman_day1.domain.server_scan_servers import MaintenanceStart
from wingman_day1.infrastructure.fake_fleet import (
    FakeServerInventory,
    default_fleet_file,
    load_fleet,
)
from wingman_day1.infrastructure.fake_server_records import default_records_file, load_records
from wingman_day1.infrastructure.fake_server_scan_events import default_events_file, load_events
from wingman_day1.infrastructure.server_scan import HttpServerInventory

VIEWER = "server-scan-viewer-token-never-shown-0002"
AUDITOR = "server-scan-auditor-token-never-shown-0004"
NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)
CISCO = "ocp-cisco-m6-site1-128c-512gb-CSFAKE0302"
FREE_DELL = "ocp-dell-r660-site1-128c-1024gb-DLFAKE0501"


def events_page() -> dict[str, Any]:
    """server-scan's ``AuditEventListResponse`` for ``GET /api/v1/events``: one job run by hand."""
    return {
        "items": [
            {
                "id": "evt_9",
                "event_type": "JOB_TRIGGERED",
                "server_id": None,
                "server_name": None,
                "actor": {"type": "USER", "id": "alice", "display": "Alice Cohen", "role": "ADMIN"},
                "request_id": "req-9",
                "created_at": "2026-11-14T08:05:00Z",
                "data": {"cronjob": "collector-openmanage-site1", "job": "manual-8kq2d"},
            }
        ],
        "page": {"next_cursor": "c2", "has_more": True, "page_size": 1, "total": 13223},
    }


def actors_answer() -> dict[str, Any]:
    """server-scan's ``EventActorListResponse``, busiest first."""
    return {
        "items": [
            {"id": "collector-openmanage", "type": "SYSTEM", "display": None, "event_count": 9120},
            {"id": "alice", "type": "USER", "display": "Alice Cohen", "event_count": 3},
        ]
    }


def make(
    *answers: httpx.Response | Exception,
    token: str = VIEWER,
    auditor: str = AUDITOR,
    metrics: WingmanMetrics | None = None,
) -> tuple[HttpServerInventory, list[httpx.Request]]:
    sent: list[httpx.Request] = []
    queue = list(answers)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    inventory = HttpServerInventory(
        base_url="http://server-scan-api.inventory.svc:8000",
        token=token,
        admin_token="server-scan-admin-token-never-shown-0003",
        auditor_token=auditor,
        metrics=metrics,
        transport=httpx.MockTransport(handler),
        timer=iter(range(1000)).__next__,
    )
    return inventory, sent


# ── The adapter ──────────────────────────────────────────────────────────────


async def test_the_trail_is_read_with_the_auditor_token_and_every_filter_given() -> None:
    inventory, sent = make(httpx.Response(200, json=events_page()))
    israel = timezone(timedelta(hours=2))
    query = EventQuery(
        server_id="srv_1",
        event_type="HEALTH_CHANGED",
        actor_id="alice",
        since=datetime(2026, 10, 1, 9, tzinfo=israel),
        until=datetime(2026, 10, 2, tzinfo=UTC),
        server_name="ocp-dell",
        cursor="c1",
        page_size=50,
    )
    page = await inventory.events(query)
    (request,) = sent
    assert (request.method, request.url.path) == ("GET", "/api/v1/events")
    assert request.headers["authorization"] == f"Bearer {AUDITOR}"
    assert dict(request.url.params) == {
        "page_size": "50",
        "server_id": "srv_1",
        "event_type": "HEALTH_CHANGED",
        "actor_id": "alice",
        "server_name": "ocp-dell",
        "cursor": "c1",
        "since": "2026-10-01T07:00:00+00:00",
        "until": "2026-10-02T00:00:00+00:00",
    }, "the times go in UTC"
    (event,) = page.items
    assert (event.event_type, event.server_id, event.actor.display) == (
        "JOB_TRIGGERED",
        None,
        "Alice Cohen",
    )
    assert (page.page.next_cursor, page.page.total) == ("c2", 13223)


async def test_only_the_filters_given_are_sent() -> None:
    inventory, sent = make(httpx.Response(200, json=events_page()))
    await inventory.events(EventQuery())
    assert dict(sent[0].url.params) == {"page_size": "50"}


async def test_the_actors_are_read_with_the_auditor_token_only() -> None:
    inventory, sent = make(httpx.Response(200, json=actors_answer()))
    actors = await inventory.event_actors()
    (request,) = sent
    assert request.url.path == "/api/v1/events/actors"
    assert request.headers["authorization"] == f"Bearer {AUDITOR}"
    assert [(a.id, a.type, a.display, a.event_count) for a in actors.items] == [
        ("collector-openmanage", "SYSTEM", None, 9120),
        ("alice", "USER", "Alice Cohen", 3),
    ]


async def test_with_auth_off_neither_read_sends_a_token() -> None:
    inventory, sent = make(
        httpx.Response(200, json=events_page()),
        httpx.Response(200, json=actors_answer()),
        token="",
        auditor="",
    )
    await inventory.events(EventQuery())
    await inventory.event_actors()
    assert all("authorization" not in request.headers for request in sent)


@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_auditor_token_names_its_setting(status: int) -> None:
    inventory, _ = make(httpx.Response(status, json={}), httpx.Response(status, json={}))
    with pytest.raises(ServerScanDeniedError, match=r"auditor token .* SERVER_SCAN_AUDITOR_TOKEN"):
        await inventory.events(EventQuery())
    with pytest.raises(ServerScanDeniedError, match="SERVER_SCAN_AUDITOR_TOKEN"):
        await inventory.event_actors()


async def test_a_cursor_server_scan_refuses_is_refused_in_its_words() -> None:
    problem = {"code": "CURSOR_INVALID", "detail": "Malformed event cursor."}
    inventory, _ = make(httpx.Response(400, json=problem), httpx.Response(400, text="no"))
    with pytest.raises(ServerScanRefusedError, match=r"^server-scan: Malformed event cursor\.$"):
        await inventory.events(EventQuery(cursor="forged"))
    with pytest.raises(ServerScanRefusedError, match="refused the events cursor"):
        await inventory.events(EventQuery(cursor="forged"))


def malformed() -> list[tuple[str, dict[str, Any]]]:
    no_time = events_page()
    no_time["items"][0]["created_at"] = None
    no_page = events_page()
    del no_page["page"]
    worded_count = actors_answer()
    worded_count["items"][0]["event_count"] = "many"
    return [("events", no_time), ("events", no_page), ("actors", worded_count)]


@pytest.mark.parametrize(("read", "raw"), malformed())
async def test_a_malformed_answer_is_unavailable_never_blank(
    read: str, raw: dict[str, Any]
) -> None:
    inventory, _ = make(httpx.Response(200, json=raw))
    with pytest.raises(ServerScanUnavailableError, match="malformed"):
        await (inventory.events(EventQuery()) if read == "events" else inventory.event_actors())


async def test_server_scan_unreachable_or_failing_is_unavailable() -> None:
    inventory, _ = make(httpx.ConnectError("refused"), httpx.Response(500, json={}))
    with pytest.raises(ServerScanUnavailableError, match="unreachable listing events"):
        await inventory.events(EventQuery())
    with pytest.raises(ServerScanUnavailableError, match="answered 500"):
        await inventory.event_actors()


async def test_each_read_is_counted_under_its_operation() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    inventory, _ = make(
        httpx.Response(200, json=events_page()),
        httpx.Response(400, json={"detail": "Malformed event cursor."}),
        httpx.Response(403, json={}),
        httpx.Response(200, json=actors_answer()),
        httpx.ConnectError("refused"),
        metrics=metrics,
    )
    await inventory.events(EventQuery())
    with pytest.raises(ServerScanRefusedError):
        await inventory.events(EventQuery(cursor="x"))
    with pytest.raises(ServerScanDeniedError):
        await inventory.events(EventQuery())
    await inventory.event_actors()
    with pytest.raises(ServerScanUnavailableError):
        await inventory.event_actors()

    def count(operation: str, outcome: str) -> float | None:
        labels = {"dependency": "server_scan", "operation": operation, "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert [count("list_events", o) for o in ("ok", "rejected", "denied")] == [1, 1, 1]
    assert [count("list_event_actors", o) for o in ("ok", "unavailable")] == [1, 1]
    assert count("list_server_events", "ok") is None, "History is its own operation"


# ── The use case ─────────────────────────────────────────────────────────────


def fixture_fleet() -> FakeServerInventory:
    rows, _ = load_fleet(default_fleet_file())
    return FakeServerInventory(
        rows,
        records=load_records(default_records_file()),
        events=load_events(default_events_file(), rows),
        clock=lambda: NOW,
    )


@pytest.mark.parametrize(
    ("viewer", "auditor", "detail"),
    [(True, True, None), (False, False, None), (False, True, None), (True, False, EVENTS_OFF)],
)
def test_events_need_the_auditor_token_beside_a_viewer_token(
    viewer: bool, auditor: bool, detail: str | None
) -> None:
    assert audit_detail("Events", viewer_token=viewer, auditor_token=auditor) == detail


def test_each_page_of_the_audit_trail_says_what_it_needs_in_one_line() -> None:
    assert EVENTS_OFF.startswith("Events needs server-scan's auditor token")
    assert HISTORY_OFF.startswith("History needs server-scan's auditor token")
    assert EVENTS_OFF.endswith("restart day1 (SERVER_SCAN_AUDITOR_TOKEN).")


async def test_the_use_case_keeps_events_off_without_the_auditor_token() -> None:
    fleet = fixture_fleet()
    service = ServerScanService(fleet, events_detail=EVENTS_OFF)
    with pytest.raises(ServerScanAuditOffError, match=r"^Events needs"):
        await service.events(EventQuery())
    with pytest.raises(ServerScanAuditOffError, match=r"^Events needs"):
        await service.event_actors()
    server_id = fleet.snapshot()[0].id
    history = await service.history(server_id, cursor=None, page_size=50)
    assert history.items, "History has its own switch"


# ── The fake ─────────────────────────────────────────────────────────────────


async def test_the_fakes_trail_comes_in_two_pages_newest_first() -> None:
    fleet = fixture_fleet()
    first = await fleet.events(EventQuery())
    assert first.page.total is not None and 50 < first.page.total <= 100
    assert first.page.has_more and len(first.items) == 50
    rest = await fleet.events(EventQuery(cursor=first.page.next_cursor))
    assert (rest.page.total, rest.page.has_more, rest.page.next_cursor) == (None, False, None)
    events = [*first.items, *rest.items]
    assert len(events) == first.page.total == len({e.id for e in events})
    times = [e.created_at for e in events]
    assert times == sorted(times, reverse=True)
    assert {e.actor.type for e in events} >= {"SYSTEM", "USER", "TOKEN"}
    assert len({e.server_id for e in events if e.server_id}) > 20


async def test_the_fake_filters_as_server_scan_does() -> None:
    fleet = fixture_fleet()

    async def kept(**filters: Any) -> list[Any]:
        return list((await fleet.events(EventQuery(page_size=200, **filters))).items)

    assert {e.event_type for e in await kept(event_type="LOGIN_SUCCEEDED")} == {"LOGIN_SUCCEEDED"}
    legacy = await kept(event_type="HEALTH_STATUS_CHANGED")
    assert legacy == await kept(event_type="HEALTH_CHANGED") and legacy
    assert {e.actor.id for e in await kept(actor_id="alice")} == {"alice"}
    assert {e.server_name for e in await kept(server_name="  CSFAKE0302 ")} == {CISCO}
    edge = datetime(2026, 11, 14, 7, 58, tzinfo=UTC)
    assert min(e.created_at for e in await kept(since=edge)) == edge, "since is inclusive"
    assert all(e.created_at < edge for e in await kept(until=edge)), "until is exclusive"
    both = await kept(actor_id="alice", event_type="TOKEN_REVOKED")
    assert [e.data.get("user") for e in both] == ["dana", "alice"]


async def test_a_servers_history_is_the_trail_by_its_id() -> None:
    fleet = fixture_fleet()
    row = next(r for r in fleet.snapshot() if r.name == FREE_DELL)
    history = await fleet.server_events(row.id, cursor=None, page_size=50)
    by_query = await fleet.events(EventQuery(server_id=row.id))
    assert history == by_query
    types = [e.event_type for e in history.items]
    assert types[:3] == ["SERVER_RELEASED", "SERVER_RESERVATION_REFUSED", "SERVER_RESERVED"]
    assert types[-1] == "SERVER_CREATED"


async def test_a_pruned_servers_events_keep_its_id_and_lose_its_name() -> None:
    fleet = fixture_fleet()
    (pruned,) = (await fleet.events(EventQuery(event_type="SERVER_PRUNED"))).items
    assert (pruned.server_id, pruned.server_name) == ("srv_00000000000000000000000000000999", None)


async def test_a_maintenance_change_in_the_fake_is_the_trails_newest_event() -> None:
    fleet = fixture_fleet()
    row = next(r for r in fleet.snapshot() if not r.maintenance)
    await fleet.start_maintenance(row.id, MaintenanceStart(reason="donor"))
    (newest,) = (await fleet.events(EventQuery(page_size=1))).items
    assert (newest.event_type, newest.server_id, newest.actor.id) == (
        "MAINTENANCE_ENABLED",
        row.id,
        "dev",
    )


async def test_the_fakes_actors_are_counted_busiest_first() -> None:
    fleet = fixture_fleet()
    actors = (await fleet.event_actors()).items
    total = (await fleet.events(EventQuery())).page.total
    assert sum(a.event_count for a in actors) == total
    counts = [(-a.event_count, a.id) for a in actors]
    assert counts == sorted(counts)
    alice = next(a for a in actors if a.id == "alice")
    assert (alice.type, alice.display) == ("USER", "Alice Cohen")
    assert {a.type for a in actors} == {"SYSTEM", "USER", "TOKEN"}


@pytest.mark.parametrize("cursor", ["3", "not-a-time|evt_1", "2026-11-14T08:00:00|evt_1"])
async def test_a_cursor_the_fake_never_made_is_refused(cursor: str) -> None:
    with pytest.raises(ServerScanRefusedError, match="Malformed event cursor"):
        await fixture_fleet().events(EventQuery(cursor=cursor))


def test_the_fixture_names_only_servers_of_the_fleet(tmp_path: Path) -> None:
    rows, _ = load_fleet(default_fleet_file())
    bad = tmp_path / "events.yaml"
    item = (
        "{event_type: SERVER_CREATED, created_at: '2026-11-01T00:00:00Z', "
        "actor: {type: SYSTEM, id: x}"
    )
    bad.write_text(f"items:\n  - {item}, server: ocp-nope}}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="'ocp-nope', which is not a server"):
        load_events(bad, rows)
    bad.write_text(f"items:\n  - {item.replace('Z', '')}}}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="needs its zone"):
        load_events(bad, rows)
    bad.write_text("events: []\n", encoding="utf-8")
    with pytest.raises(TypeError, match="'items' list"):
        load_events(bad, rows)
