"""The FastAPI app every service starts from.

``create_base_app`` wires what each service must have and none may forget:
RFC 9457 errors (ADR-0004), request ids, metrics and ``/metrics``
(ADR-0010), session tokens for ``CurrentUser``/``AdminUser``, and health:

- ``/health/live`` and ``/healthz`` (the chart's existing probe path): the
  process serves requests. Never checks dependencies, so a GitLab outage does
  not restart every pod.
- ``/health/ready``: each readiness check passes within a timeout. Its body is
  a plain object, not a problem document: it is read by probes, not by the
  web app (as in server-scan). A check wrapped in :func:`ready_once` (GitLab,
  in both services) runs only until it first passes: a pod GitLab refuses
  never becomes ready, and a later outage does not take every pod out of the
  Service at once, since the requests report it themselves (ADR-0054).
- ``<api_prefix>/build`` (any logged-in user): the ``version`` and ``commit``
  the service runs, as ``wingman_build_info`` reports them; the web's settings
  page shows them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Final

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from wingman_core.infrastructure.session_tokens import SessionTokens
from wingman_core.observability.metrics import WingmanMetrics
from wingman_core.web.auth import CurrentUser
from wingman_core.web.exception_handlers import register_exception_handlers
from wingman_core.web.metrics import install_metrics
from wingman_core.web.request_context import RequestIdMiddleware

ReadinessCheck = Callable[[], Awaitable[object]]
"""Raises (or times out) when a dependency is not usable."""

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]

READINESS_TIMEOUT_SECONDS: Final = 3.0


def ready_once(check: ReadinessCheck) -> ReadinessCheck:
    """``check`` until it has passed once in this process; after that, a pass without running it.

    For a dependency a pod needs to start serving whose later outages the
    requests themselves report as problems: GitLab (ADR-0054). Until the first
    pass, every probe runs ``check`` under the readiness timeout, and one that
    fails or times out leaves it unpassed. Probes that overlap before then each
    run it.
    """
    passed = False

    async def until_passed() -> None:
        nonlocal passed
        if not passed:
            await check()
            passed = True

    return until_passed


def create_base_app(
    *,
    title: str,
    version: str,
    commit: str,
    api_prefix: str,
    metrics: WingmanMetrics,
    session_tokens: SessionTokens,
    readiness: Mapping[str, ReadinessCheck] | None = None,
    lifespan: Lifespan | None = None,
) -> FastAPI:
    """A FastAPI app with Wingman's middleware, handlers, metrics and health routes.

    ``api_prefix`` is where the service's routes live (``/api/day1``); the
    build route goes under it, so the proxy in front routes it like the rest.
    There is no CORS: the web app is served from the same origin as the API
    (the legacy services allowed ``*`` with credentials).
    """
    app = FastAPI(title=title, version=version, lifespan=lifespan)
    app.state.metrics = metrics
    app.state.session_tokens = session_tokens
    install_metrics(app, metrics)
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    _add_health_routes(app, dict(readiness or {}))
    _add_build_route(app, f"{api_prefix.rstrip('/')}/build", version=version, commit=commit)
    return app


def _add_build_route(app: FastAPI, path: str, *, version: str, commit: str) -> None:
    @app.get(path, tags=["build"])
    async def build(_: CurrentUser) -> dict[str, str]:
        """The build this service runs (``WINGMAN_VERSION``, ``WINGMAN_COMMIT``)."""
        return {"version": version, "commit": commit}


def _add_health_routes(app: FastAPI, checks: dict[str, ReadinessCheck]) -> None:
    @app.get("/health/live", include_in_schema=False)
    @app.get("/healthz", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        results = await asyncio.gather(*(_run(check) for check in checks.values()))
        report = dict(zip(checks, results, strict=True))
        ok = all(result == "ok" for result in results)
        return JSONResponse(
            status_code=200 if ok else 503,
            content={"status": "ready" if ok else "not_ready", "checks": report},
        )


async def _run(check: ReadinessCheck) -> str:
    try:
        await asyncio.wait_for(check(), timeout=READINESS_TIMEOUT_SECONDS)
    except TimeoutError:
        return "timeout"
    except Exception as exc:  # noqa: BLE001 - a readiness check reports any failure, never raises
        return f"error: {type(exc).__name__}"
    return "ok"
