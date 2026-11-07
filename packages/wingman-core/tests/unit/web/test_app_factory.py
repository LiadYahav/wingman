from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import CollectorRegistry

from wingman_core.application.approvals import SelfApprovalError, UnmanagedProjectError
from wingman_core.infrastructure.session_tokens import SessionTokens
from wingman_core.observability.metrics import WingmanMetrics
from wingman_core.web import app_factory
from wingman_core.web.app_factory import ReadinessCheck, create_base_app


def make_app(
    *,
    readiness: Mapping[str, ReadinessCheck] | None = None,
    cors_origins: Sequence[str] = (),
) -> FastAPI:
    return create_base_app(
        title="t",
        version="0",
        metrics=WingmanMetrics(CollectorRegistry(), component="t", version="0", commit="0"),
        session_tokens=SessionTokens("s" * 40, ttl=timedelta(hours=1)),
        readiness=readiness,
        cors_origins=cors_origins,
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


async def test_wildcard_cors_is_refused_and_explicit_origins_work() -> None:
    with pytest.raises(ValueError, match="explicit"):
        make_app(cors_origins=["*"])
    app = make_app(cors_origins=["https://wingman.example"])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        response = await client.get("/healthz", headers={"origin": "https://wingman.example"})
    assert response.headers["access-control-allow-origin"] == "https://wingman.example"


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
