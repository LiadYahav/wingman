"""A server's maintenance on and off, the Server Scan area's one write (ADR-0048, 3.23.0).

The adapter against server-scan's answers (MockTransport): the admin token on
the writes only, none against a server-scan with auth off; allowed, refused,
not found, unanswered; sent exactly once whatever happens (ADR-0006). The
cache clears the rows and sites after a write; the fake changes its row; the
use case refuses without the admin token and logs every write with the person.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.domain.users import Role, User
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.application.server_scan import ServerScanService
from wingman_day1.domain.errors import (
    AmbiguousServerScanWriteError,
    ServerNotFoundError,
    ServerScanDeniedError,
    ServerScanRefusedError,
    ServerScanUnavailableError,
    ServerScanWritesOffError,
)
from wingman_day1.domain.server_scan_servers import (
    MAINTENANCE_OFF,
    MaintenanceStart,
    ServerMaintenance,
    maintenance_detail,
)
from wingman_day1.infrastructure.cached_server_scan import CachedServerInventory
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.server_scan import HttpServerInventory
from wingman_day1.infrastructure.server_scan_parse import server_row

VIEWER = "server-scan-viewer-token-never-shown-0002"
ADMIN = "server-scan-admin-token-never-shown-0003"
SERVER_ID = "srv_d226c05c968244e19f68e4aa8f16bad3"
NAME = "ocp-cisco-m6-bat-yam-128c-128gb-CIS0000630"
PATH = f"/api/v1/servers/{SERVER_ID}/maintenance"
START = MaintenanceStart(
    reason="Replacing PSU 2 — INC-4417", expected_end=datetime(2026, 11, 14, 16, tzinfo=UTC)
)
ALICE = User(username="alice", role=Role.ADMIN)


def detail(enabled: bool, reason: str | None = None) -> dict[str, Any]:
    """server-scan's ServerDetail, as much of it as the answer is read for."""
    return {
        "id": SERVER_ID,
        "name": NAME,
        "maintenance": {
            "enabled": enabled,
            "reason": reason,
            "created_by": "api-token-admin" if enabled else None,
            "expected_end": None,
        },
        "health": {"overall": "HEALTHY"},
    }


def make(
    *answers: httpx.Response | Exception,
    token: str = VIEWER,
    admin_token: str = ADMIN,
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
        admin_token=admin_token,
        metrics=metrics,
        transport=httpx.MockTransport(handler),
        timer=iter(range(1000)).__next__,
    )
    return inventory, sent


async def test_starting_puts_the_reason_and_end_with_the_admin_token() -> None:
    inventory, sent = make(httpx.Response(200, json=detail(True, START.reason)))
    change = await inventory.start_maintenance(SERVER_ID, START)
    assert change == ServerMaintenance(SERVER_ID, NAME, True, START.reason, "api-token-admin")
    (request,) = sent
    assert (request.method, request.url.path) == ("PUT", PATH)
    assert request.headers["authorization"] == f"Bearer {ADMIN}"
    assert json.loads(request.content) == {
        "reason": "Replacing PSU 2 — INC-4417",
        "expected_end": "2026-11-14T16:00:00+00:00",
    }


async def test_a_start_without_a_reason_or_end_sends_an_empty_body() -> None:
    inventory, sent = make(httpx.Response(200, json=detail(True)))
    await inventory.start_maintenance(SERVER_ID, MaintenanceStart())
    assert json.loads(sent[0].content) == {}


async def test_ending_deletes_with_the_admin_token_and_no_body() -> None:
    inventory, sent = make(httpx.Response(200, json=detail(False)))
    change = await inventory.end_maintenance(SERVER_ID)
    assert (change.enabled, change.reason, change.created_by) == (False, None, None)
    assert (sent[0].method, sent[0].url.path, sent[0].content) == ("DELETE", PATH, b"")
    assert sent[0].headers["authorization"] == f"Bearer {ADMIN}"


async def test_reads_keep_the_viewer_token() -> None:
    inventory, sent = make(httpx.Response(200, json={"items": [], "generated_at": None}))
    await inventory.fleet()
    assert sent[0].headers["authorization"] == f"Bearer {VIEWER}"


async def test_against_a_server_scan_with_auth_off_no_token_is_sent() -> None:
    inventory, sent = make(httpx.Response(200, json=detail(True)), token="", admin_token="")
    await inventory.start_maintenance(SERVER_ID, START)
    assert "authorization" not in sent[0].headers


async def test_an_id_is_one_path_segment() -> None:
    inventory, sent = make(httpx.Response(200, json=detail(False)))
    await inventory.end_maintenance("srv/../x")
    assert sent[0].url.raw_path == b"/api/v1/servers/srv%2F..%2Fx/maintenance"


@pytest.mark.parametrize(
    ("answer", "error", "words"),
    [
        (httpx.Response(404), ServerNotFoundError, "no server"),
        (httpx.Response(401), ServerScanDeniedError, "SERVER_SCAN_ADMIN_TOKEN"),
        (httpx.Response(403), ServerScanDeniedError, "SERVER_SCAN_ADMIN_TOKEN"),
        (httpx.Response(500), ServerScanUnavailableError, "answered 500"),
        (httpx.Response(503), ServerScanUnavailableError, "answered 503"),
        (httpx.ConnectError("refused"), ServerScanUnavailableError, "nothing changed"),
        (httpx.ConnectTimeout("slow"), ServerScanUnavailableError, "nothing changed"),
        (httpx.ReadTimeout("lost"), AmbiguousServerScanWriteError, "no answer came back"),
        (httpx.RemoteProtocolError("cut"), AmbiguousServerScanWriteError, "may have changed"),
        (httpx.Response(504), AmbiguousServerScanWriteError, "gateway timed out"),
        (httpx.Response(200, json={"id": SERVER_ID}), AmbiguousServerScanWriteError, "(200)"),
        (httpx.Response(200, text="<html>"), AmbiguousServerScanWriteError, "(200)"),
    ],
)
async def test_every_failure_is_named_and_the_write_is_sent_once(
    answer: httpx.Response | Exception, error: type[Exception], words: str
) -> None:
    for write in ("start", "end"):
        inventory, sent = make(answer)
        with pytest.raises(error, match=words.replace("(", r"\(").replace(")", r"\)")):
            if write == "start":
                await inventory.start_maintenance(SERVER_ID, START)
            else:
                await inventory.end_maintenance(SERVER_ID)
        assert len(sent) == 1, "a write is never retried (ADR-0006)"


async def test_a_refused_body_carries_server_scans_words() -> None:
    refusal = httpx.Response(422, json={"detail": "expected_end is in the past"})
    inventory, _ = make(refusal)
    with pytest.raises(ServerScanRefusedError) as raised:
        await inventory.start_maintenance(SERVER_ID, START)
    assert raised.value.problems == ("expected_end is in the past",)


async def test_writes_are_counted_by_operation_and_outcome() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    inventory, _ = make(
        httpx.Response(200, json=detail(True)),
        httpx.ReadTimeout("lost"),
        httpx.Response(403),
        metrics=metrics,
    )
    await inventory.start_maintenance(SERVER_ID, START)
    with pytest.raises(AmbiguousServerScanWriteError):
        await inventory.end_maintenance(SERVER_ID)
    with pytest.raises(ServerScanDeniedError):
        await inventory.start_maintenance(SERVER_ID, START)

    def count(operation: str, outcome: str) -> float | None:
        labels = {"dependency": "server_scan", "operation": operation, "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert count("enable_maintenance", "ok") == 1
    assert count("disable_maintenance", "ambiguous") == 1
    assert count("enable_maintenance", "denied") == 1


def fleet_row(**changes: Any) -> Any:
    raw = {
        "id": SERVER_ID,
        "name": NAME,
        "vendor": "cisco",
        "health": "HEALTHY",
        "openshift_state": "AVAILABLE",
        "reachable": True,
        "stale": False,
        "maintenance": {"enabled": False, "reason": None, "created_by": None},
        **changes,
    }
    return server_row(raw)


async def test_a_write_clears_the_cached_rows_and_sites_whatever_its_outcome() -> None:
    fake = FakeServerInventory([fleet_row()])
    cached = CachedServerInventory(fake, TtlCache(), ttl=30)
    assert not (await cached.rows())[0].maintenance
    await cached.sites()
    await cached.start_maintenance(SERVER_ID, START)
    assert (await cached.rows())[0].maintenance, "the next read shows the write"
    assert (await cached.sites()).fleet.in_maintenance == 1
    fake.unavailable = True
    with pytest.raises(ServerScanUnavailableError):
        await cached.end_maintenance(SERVER_ID)
    with pytest.raises(ServerScanUnavailableError):
        await cached.rows()


async def test_the_fake_keeps_who_started_it_and_forgets_on_end() -> None:
    fake = FakeServerInventory([fleet_row()])
    first = await fake.start_maintenance(SERVER_ID, START)
    assert (first.enabled, first.reason, first.created_by) == (True, START.reason, "dev")
    fake.replace(fleet_row(maintenance={"enabled": True, "reason": "old", "created_by": "ops"}))
    again = await fake.start_maintenance(SERVER_ID, MaintenanceStart(reason="new"))
    assert (again.reason, again.created_by) == ("new", "ops")
    ended = await fake.end_maintenance(SERVER_ID)
    assert (ended.enabled, ended.reason, ended.created_by) == (False, None, None)
    row = (await fake.rows())[0]
    assert (row.maintenance, row.maintenance_reason, row.maintenance_by) == (False, None, None)
    assert [start for _, start in fake.maintenance_starts] == [START, MaintenanceStart("new")]
    with pytest.raises(ServerNotFoundError):
        await fake.end_maintenance("srv_unknown")


@pytest.mark.parametrize(
    ("viewer", "admin", "off"),
    [(True, True, False), (False, True, False), (False, False, False), (True, False, True)],
)
def test_the_toggle_is_off_only_with_a_viewer_token_and_no_admin_token(
    viewer: bool, admin: bool, off: bool
) -> None:
    expected = MAINTENANCE_OFF if off else None
    assert maintenance_detail(viewer_token=viewer, admin_token=admin) == expected


async def test_without_the_admin_token_nothing_is_sent() -> None:
    fake = FakeServerInventory([fleet_row()])
    service = ServerScanService(fake, maintenance_detail=MAINTENANCE_OFF)
    with pytest.raises(ServerScanWritesOffError, match="SERVER_SCAN_ADMIN_TOKEN"):
        await service.start_maintenance(SERVER_ID, START, user=ALICE)
    with pytest.raises(ServerScanWritesOffError):
        await service.end_maintenance(SERVER_ID, user=ALICE)
    assert fake.maintenance_starts == []
    assert not (await fake.rows())[0].maintenance


async def test_every_write_is_logged_with_the_person(caplog: pytest.LogCaptureFixture) -> None:
    service = ServerScanService(FakeServerInventory([fleet_row()]))
    with caplog.at_level(logging.INFO, logger="wingman_day1.application.server_scan"):
        await service.start_maintenance(SERVER_ID, START, user=ALICE)
        await service.end_maintenance(SERVER_ID, user=ALICE)
    started, ended = caplog.records
    assert started.__dict__["event"] == "server_maintenance_started"
    assert (started.__dict__["user"], started.__dict__["server_name"]) == ("alice", NAME)
    assert started.__dict__["reason"] == START.reason
    assert started.__dict__["expected_end"] == "2026-11-14T16:00:00+00:00"
    assert ended.__dict__["event"] == "server_maintenance_ended"
    assert "user=alice" in ended.getMessage()


async def test_an_unanswered_write_is_logged_unconfirmed_and_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    inventory, sent = make(httpx.ReadTimeout("lost"))
    service = ServerScanService(inventory)
    with (
        caplog.at_level(logging.INFO, logger="wingman_day1.application.server_scan"),
        pytest.raises(AmbiguousServerScanWriteError),
    ):
        await service.end_maintenance(SERVER_ID, user=ALICE)
    (record,) = caplog.records
    assert (record.levelno, record.__dict__["event"]) == (
        logging.WARNING,
        "server_maintenance_unconfirmed",
    )
    assert record.__dict__["user"] == "alice"
    assert len(sent) == 1
