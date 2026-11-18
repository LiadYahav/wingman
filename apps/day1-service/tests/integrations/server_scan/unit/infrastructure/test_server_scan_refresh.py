"""Fetch now: one server read from its vendor manager now (ADR-0048's v6.6.0 amendment).

server-scan v6.5.0's ``POST /api/v1/servers/{id}/refresh`` (its ADR-0064),
against its answers (MockTransport): the admin token, no body, day1's own
longer wait; the answer read as the server page's record; every refusal in
server-scan's words; sent exactly once whatever happens (ADR-0006). The cache
clears the rows and sites after one; the fake reads its server back seen now
and refuses those server-scan cannot read; the use case is off without the
admin token and logs every Fetch now with the person.

What it follows upstream, and at which version: docs/integrations/server-scan.yaml.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.domain.users import Role, User
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import (
    AmbiguousServerScanWriteError,
    ServerNotFoundError,
    ServerScanDeniedError,
    ServerScanRefreshRefusedError,
    ServerScanUnavailableError,
    ServerScanWritesOffError,
)
from wingman_day1.integrations.server_scan.application.area import ServerScanService
from wingman_day1.integrations.server_scan.domain.servers import REFRESH_OFF, refresh_detail
from wingman_day1.integrations.server_scan.infrastructure.adapter import HttpServerInventory
from wingman_day1.integrations.server_scan.infrastructure.cached import CachedServerInventory
from wingman_day1.integrations.server_scan.infrastructure.fakes.inventory import FakeServerInventory
from wingman_day1.integrations.server_scan.infrastructure.fakes.records import FakeRecords
from wingman_day1.integrations.server_scan.infrastructure.parse import server_row
from wingman_day1.integrations.server_scan.infrastructure.writes import REFRESH_TIMEOUT_SECONDS

VIEWER = "server-scan-viewer-token-never-shown-0002"
ADMIN = "server-scan-admin-token-never-shown-0003"
SERVER_ID = "srv_d226c05c968244e19f68e4aa8f16bad3"
NAME = "ocp-dell-r660-site1-128c-1024gb-DLFAKE0101"
PATH = f"/api/v1/servers/{SERVER_ID}/refresh"
NOW = datetime(2026, 11, 18, 9, tzinfo=UTC)
SEEN = datetime(2026, 11, 18, 3, tzinfo=UTC)
ALICE = User(username="alice", role=Role.ADMIN)


def fleet_row(**changes: Any) -> Any:
    raw = {
        "id": SERVER_ID,
        "name": NAME,
        "vendor": "dell",
        "model": "PowerEdge R660",
        "source_provider": "OPENMANAGE",
        "health": "HEALTHY",
        "openshift_state": "AVAILABLE",
        "reachable": True,
        "stale": True,
        "last_seen_at": SEEN.isoformat(),
        "maintenance": {"enabled": False, "reason": None, "created_by": None},
        **changes,
    }
    return server_row(raw)


def detail(revision: int = 4) -> dict[str, Any]:
    """server-scan's ``ServerDetail`` of the server, in its shape (the fake builds it)."""
    record = FakeRecords().record(fleet_row(), NOW)
    return record.model_dump(mode="json") | {"revision": revision, "schema_version": 3}


def problem(status: int, code: str, words: str) -> httpx.Response:
    body = {"type": f"/problems/{code.lower()}", "status": status, "detail": words, "code": code}
    return httpx.Response(status, json=body)


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
        clock=lambda: NOW,
    )
    return inventory, sent


# ── The adapter ──────────────────────────────────────────────────────────────


async def test_a_fetch_posts_once_with_the_admin_token_and_reads_the_record() -> None:
    inventory, sent = make(httpx.Response(200, json=detail(revision=5)))
    record = await inventory.refresh(SERVER_ID)
    (request,) = sent
    assert (request.method, request.url.path, request.content) == ("POST", PATH, b"")
    assert request.headers["authorization"] == f"Bearer {ADMIN}"
    assert (record.id, record.name, record.revision) == (SERVER_ID, NAME, 5)
    assert record.reservation.held is False


async def test_a_fetch_waits_longer_than_a_read_for_the_manager() -> None:
    """server-scan waits up to its recheck timeout (UCS Central 240 s); day1 up to 120 s."""
    inventory, sent = make(httpx.Response(200, json=detail()))
    await inventory.refresh(SERVER_ID)
    assert sent[0].extensions["timeout"]["read"] == REFRESH_TIMEOUT_SECONDS
    assert REFRESH_TIMEOUT_SECONDS < 130, "under nginx's and the Route's 130 s for the path"


async def test_against_a_server_scan_with_auth_off_no_token_is_sent() -> None:
    inventory, sent = make(httpx.Response(200, json=detail()), token="", admin_token="")
    await inventory.refresh(SERVER_ID)
    assert "authorization" not in sent[0].headers


async def test_an_id_is_one_path_segment() -> None:
    inventory, sent = make(httpx.Response(200, json=detail()))
    await inventory.refresh("srv/../x")
    assert sent[0].url.raw_path == b"/api/v1/servers/srv%2F..%2Fx/refresh"


@pytest.mark.parametrize(
    ("code", "words"),
    [
        (
            "SERVER_REFRESH_UNSUPPORTED",
            "The API is not connected to the REDFISH_STANDALONE manager that collects 'x'; "
            "run its collector job instead.",
        ),
        ("SERVER_NOT_AT_MANAGER", "The ONEVIEW manager no longer reports 'x'; the stored data"),
    ],
)
async def test_a_refusal_is_server_scans_words(code: str, words: str) -> None:
    inventory, _ = make(problem(409, code, words))
    with pytest.raises(ServerScanRefreshRefusedError) as raised:
        await inventory.refresh(SERVER_ID)
    assert str(raised.value) == f"server-scan: {words}"


@pytest.mark.parametrize(
    ("answer", "error", "words"),
    [
        (problem(404, "NOT_FOUND", "No server with id 'x'."), ServerNotFoundError, "No server"),
        (httpx.Response(404), ServerNotFoundError, "no server"),
        (httpx.Response(409), ServerScanRefreshRefusedError, "refused reading"),
        (
            problem(503, "SERVICE_UNAVAILABLE", "The ONEVIEW manager could not be reached"),
            ServerScanUnavailableError,
            "vendor manager: The ONEVIEW manager could not be reached",
        ),
        (httpx.Response(503), ServerScanUnavailableError, "nothing changed"),
        (httpx.Response(401), ServerScanDeniedError, "SERVER_SCAN_ADMIN_TOKEN"),
        (httpx.Response(403), ServerScanDeniedError, "SERVER_SCAN_ADMIN_TOKEN"),
        (httpx.Response(500), ServerScanUnavailableError, "answered 500"),
        (httpx.ConnectError("refused"), ServerScanUnavailableError, "nothing changed"),
        (httpx.ReadTimeout("lost"), AmbiguousServerScanWriteError, "last seen"),
        (httpx.RemoteProtocolError("cut"), AmbiguousServerScanWriteError, "no answer came back"),
        (httpx.Response(504), AmbiguousServerScanWriteError, "gateway timed out"),
        (httpx.Response(200, json={"id": SERVER_ID}), AmbiguousServerScanWriteError, "(200)"),
    ],
)
async def test_every_failure_is_named_and_the_fetch_is_sent_once(
    answer: httpx.Response | Exception, error: type[Exception], words: str
) -> None:
    inventory, sent = make(answer)
    with pytest.raises(error, match=words.replace("(", r"\(").replace(")", r"\)")):
        await inventory.refresh(SERVER_ID)
    assert len(sent) == 1, "a write is never retried (ADR-0006)"


async def test_fetches_are_counted_by_outcome() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    inventory, _ = make(
        httpx.Response(200, json=detail()),
        problem(409, "SERVER_NOT_AT_MANAGER", "gone"),
        httpx.ReadTimeout("lost"),
        metrics=metrics,
    )
    await inventory.refresh(SERVER_ID)
    with pytest.raises(ServerScanRefreshRefusedError):
        await inventory.refresh(SERVER_ID)
    with pytest.raises(AmbiguousServerScanWriteError):
        await inventory.refresh(SERVER_ID)

    def count(outcome: str) -> float | None:
        labels = {"dependency": "server_scan", "operation": "refresh_server", "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert (count("ok"), count("rejected"), count("ambiguous")) == (1, 1, 1)


# ── The cache and the fake ───────────────────────────────────────────────────


async def test_a_fetch_clears_the_cached_rows_and_sites_whatever_its_outcome() -> None:
    fake = FakeServerInventory([fleet_row()], clock=lambda: NOW)
    cached = CachedServerInventory(fake, TtlCache(), ttl=30)
    assert (await cached.rows())[0].last_seen_at == SEEN
    await cached.refresh(SERVER_ID)
    assert (await cached.rows())[0].last_seen_at == NOW, "the next read shows it"
    fake.unavailable = True
    with pytest.raises(ServerScanUnavailableError):
        await cached.refresh(SERVER_ID)
    with pytest.raises(ServerScanUnavailableError):
        await cached.rows()


async def test_the_fake_reads_its_server_back_seen_now_and_unchanged() -> None:
    fake = FakeServerInventory([fleet_row()], clock=lambda: NOW)
    before = await fake.record(SERVER_ID)
    record = await fake.refresh(SERVER_ID)
    assert (record.last_seen_at, record.stale, record.revision) == (NOW, False, before.revision)
    page = await fake.server_events(SERVER_ID, cursor=None, page_size=50)
    newest = page.items[0]
    assert (newest.event_type, newest.actor.id) == ("SERVER_REFRESHED", "dev")
    assert newest.data == {"manager_type": "OPENMANAGE", "changed": False}
    assert fake.refreshes == [SERVER_ID]


@pytest.mark.parametrize(
    ("provider", "words"),
    [
        (None, "was not collected by a vendor manager"),
        ("REDFISH_STANDALONE", "run its collector job instead"),
    ],
)
async def test_the_fake_refuses_what_server_scan_cannot_read(
    provider: str | None, words: str
) -> None:
    fake = FakeServerInventory([fleet_row(source_provider=provider)], clock=lambda: NOW)
    with pytest.raises(ServerScanRefreshRefusedError, match=words):
        await fake.refresh(SERVER_ID)
    assert (await fake.rows())[0].last_seen_at == SEEN
    with pytest.raises(ServerNotFoundError):
        await fake.refresh("srv_unknown")


# ── The use case ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("viewer", "admin", "off"),
    [(True, True, False), (False, True, False), (False, False, False), (True, False, True)],
)
def test_fetch_now_is_off_only_with_a_viewer_token_and_no_admin_token(
    viewer: bool, admin: bool, off: bool
) -> None:
    expected = REFRESH_OFF if off else None
    assert refresh_detail(viewer_token=viewer, admin_token=admin) == expected


async def test_without_the_admin_token_nothing_is_sent() -> None:
    fake = FakeServerInventory([fleet_row()], clock=lambda: NOW)
    service = ServerScanService(fake, refresh_detail=REFRESH_OFF)
    with pytest.raises(ServerScanWritesOffError, match="SERVER_SCAN_ADMIN_TOKEN"):
        await service.refresh(SERVER_ID, user=ALICE)
    assert fake.refreshes == []


async def test_every_fetch_is_logged_with_the_person(caplog: pytest.LogCaptureFixture) -> None:
    service = ServerScanService(FakeServerInventory([fleet_row()], clock=lambda: NOW))
    with caplog.at_level(logging.INFO, logger="wingman_day1.application.server_scan"):
        await service.refresh(SERVER_ID, user=ALICE)
    (line,) = caplog.records
    assert line.__dict__["event"] == "server_refreshed"
    assert (line.__dict__["user"], line.__dict__["server_name"]) == ("alice", NAME)
    assert line.__dict__["revision"] == "1"


async def test_an_unanswered_fetch_is_logged_unconfirmed_and_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    inventory, sent = make(httpx.ReadTimeout("lost"))
    service = ServerScanService(inventory)
    with (
        caplog.at_level(logging.INFO, logger="wingman_day1.application.server_scan"),
        pytest.raises(AmbiguousServerScanWriteError),
    ):
        await service.refresh(SERVER_ID, user=ALICE)
    (line,) = caplog.records
    assert (line.levelno, line.__dict__["event"]) == (logging.WARNING, "server_refresh_unconfirmed")
    assert line.__dict__["user"] == "alice"
    assert len(sent) == 1
