from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import CollectorRegistry

from wingman_core.application.approvals import SelfApprovalError, UnmanagedProjectError
from wingman_core.domain.users import Role, User
from wingman_core.infrastructure.session_tokens import SessionTokens
from wingman_core.observability.metrics import WingmanMetrics
from wingman_core.web import app_factory
from wingman_core.web.app_factory import ReadinessCheck, create_base_app, ready_once


def make_app(*, readiness: Mapping[str, ReadinessCheck] | None = None) -> FastAPI:
    return create_base_app(
        title="t",
        version="1.4.0",
        commit="abc1234",
        api_prefix="/api/t/",
        metrics=WingmanMetrics(CollectorRegistry(), component="t", version="0", commit="0"),
        session_tokens=SessionTokens("s" * 40, ttl=timedelta(hours=1)),
        readiness=readiness,
    )


async def get(app: FastAPI, path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        return await client.get(path)


async def test_liveness_never_checks_dependencies() -> None:
    async def broken() -> None:
        raise RuntimeError("gitlab down")

    app = make_app(readiness={"gitlab": broken})
    for path in ("/healthz", "/health/live"):
        response = await get(app, path)
        assert (response.status_code, response.json()) == (200, {"status": "ok"})


async def test_readiness_reports_each_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_factory, "READINESS_TIMEOUT_SECONDS", 0.05)

    async def ok() -> None:
        return None

    async def broken() -> None:
        raise ConnectionError("refused")

    async def slow() -> None:
        await asyncio.sleep(1)

    ready = await get(make_app(readiness={"gitlab": ok}), "/health/ready")
    assert (ready.status_code, ready.json()) == (
        200,
        {"status": "ready", "checks": {"gitlab": "ok"}},
    )
    not_ready = await get(
        make_app(readiness={"gitlab": ok, "b": broken, "c": slow}), "/health/ready"
    )
    assert not_ready.status_code == 503
    assert not_ready.json()["checks"] == {
        "gitlab": "ok",
        "b": "error: ConnectionError",
        "c": "timeout",
    }


class Dependency:
    """A readiness check that fails, hangs or passes as the test says, and counts its calls."""

    def __init__(self) -> None:
        self.calls = 0
        self.outcome: str = "down"

    async def check(self) -> None:
        self.calls += 1
        if self.outcome == "slow":
            await asyncio.sleep(1)
        elif self.outcome == "down":
            raise ConnectionError("refused")


async def test_a_ready_once_check_fails_until_it_first_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_factory, "READINESS_TIMEOUT_SECONDS", 0.05)
    gitlab = Dependency()
    app = make_app(readiness={"gitlab": ready_once(gitlab.check)})

    for _ in range(2):
        down = await get(app, "/health/ready")
        assert (down.status_code, down.json()) == (
            503,
            {"status": "not_ready", "checks": {"gitlab": "error: ConnectionError"}},
        )
    assert gitlab.calls == 2, "every probe asks until the first pass"

    gitlab.outcome = "up"
    ready = await get(app, "/health/ready")
    assert (ready.status_code, ready.json()) == (
        200,
        {"status": "ready", "checks": {"gitlab": "ok"}},
    )
    assert gitlab.calls == 3


async def test_after_its_first_pass_a_ready_once_check_is_never_run_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_factory, "READINESS_TIMEOUT_SECONDS", 0.05)
    gitlab = Dependency()
    gitlab.outcome = "up"
    app = make_app(readiness={"gitlab": ready_once(gitlab.check)})
    assert (await get(app, "/health/ready")).status_code == 200

    for outcome in ("down", "slow"):
        gitlab.outcome = outcome
        later = await get(app, "/health/ready")
        assert (later.status_code, later.json()) == (
            200,
            {"status": "ready", "checks": {"gitlab": "ok"}},
        )
    assert gitlab.calls == 1, "a pod that was ready once does not ask the dependency again"


async def test_the_timeout_applies_to_a_ready_once_check_before_its_first_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_factory, "READINESS_TIMEOUT_SECONDS", 0.05)
    gitlab = Dependency()
    gitlab.outcome = "slow"
    app = make_app(readiness={"gitlab": ready_once(gitlab.check)})

    slow = await get(app, "/health/ready")
    assert (slow.status_code, slow.json()["checks"]) == (503, {"gitlab": "timeout"})

    gitlab.outcome = "up"
    assert (await get(app, "/health/ready")).status_code == 200, "a timeout is not a pass"
    assert gitlab.calls == 2


async def test_only_the_wrapped_check_stops_running() -> None:
    gitlab, other = Dependency(), Dependency()
    gitlab.outcome = other.outcome = "up"
    app = make_app(readiness={"gitlab": ready_once(gitlab.check), "other": other.check})
    for _ in range(3):
        assert (await get(app, "/health/ready")).status_code == 200
    assert (gitlab.calls, other.calls) == (1, 3)


async def test_the_build_is_shown_to_a_logged_in_user_under_the_api_prefix() -> None:
    app = make_app()
    assert (await get(app, "/api/t/build")).status_code == 401
    token = SessionTokens("s" * 40, ttl=timedelta(hours=1)).issue(User("ann", Role.VIEWER))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        response = await client.get("/api/t/build", headers={"authorization": f"Bearer {token}"})
    assert (response.status_code, response.json()) == (
        200,
        {"version": "1.4.0", "commit": "abc1234"},
    )


async def test_no_origin_is_allowed_cross_origin() -> None:
    # The legacy services answered CORS "*" with credentials; the web app is same-origin.
    response = await get(make_app(), "/healthz")
    assert "access-control-allow-origin" not in response.headers


async def test_approval_errors_become_problems() -> None:
    app = make_app()

    @app.get("/self")
    async def self_approval() -> None:
        raise SelfApprovalError("jane requested 7!3")

    @app.get("/unmanaged")
    async def unmanaged() -> None:
        raise UnmanagedProjectError("project 9 is not managed here")

    own = await get(app, "/self")
    assert (own.status_code, own.json()["code"]) == (403, "SELF_APPROVAL")
    other = await get(app, "/unmanaged")
    assert (other.status_code, other.json()["code"]) == (404, "NOT_FOUND")
    metrics = await get(app, "/metrics")
    assert "wingman_http_requests_total" in metrics.text
