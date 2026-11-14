"""Every error leaves as an RFC 9457 problem with a request id."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from wingman_core.domain.errors import AmbiguousWriteError, NotFoundError, RevisionConflictError
from wingman_core.web.errors import (
    AddServerAlreadyRunning,
    AppError,
    DependencyUnavailable,
    ErrorCode,
    FeatureDisabled,
    JobAlreadyRunning,
    NodeNotInCluster,
    UninstallAlreadyRunning,
    UpgradeAlreadyRunning,
    UpgradeDecisionRefused,
    UpgradeTargetsRefused,
    ValidationFailed,
)
from wingman_core.web.exception_handlers import (
    PROBLEM_JSON,
    register_domain_errors,
    register_exception_handlers,
)
from wingman_core.web.request_context import RequestIdMiddleware


class Body(BaseModel):
    replicas: int


def make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    @app.get("/app-error")
    async def app_error() -> None:
        raise ValidationFailed("name is off-convention", details={"field": "name"})

    @app.get("/git/{kind}")
    async def git_error(kind: str) -> None:
        raise {
            "missing": NotFoundError("gone"),
            "stale": RevisionConflictError("moved"),
            "ambiguous": AmbiguousWriteError("maybe"),
        }[kind]

    @app.post("/validate")
    async def validate(body: Body) -> Body:
        return body

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internals")

    return app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=make_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_app_error_is_a_problem_document(client: httpx.AsyncClient) -> None:
    response = await client.get("/app-error", headers={"x-request-id": "req-from-caller"})
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.headers["x-request-id"] == "req-from-caller"
    assert response.json() == {
        "type": "/problems/validation-error",
        "title": "Validation Error",
        "status": 422,
        "detail": "name is off-convention",
        "instance": "/app-error",
        "code": "VALIDATION_ERROR",
        "request_id": "req-from-caller",
        "details": {"field": "name"},
    }


@pytest.mark.parametrize(
    ("kind", "status", "code"),
    [
        ("missing", 404, ErrorCode.NOT_FOUND),
        ("stale", 409, ErrorCode.REVISION_CONFLICT),
        ("ambiguous", 504, ErrorCode.AMBIGUOUS_WRITE),
    ],
)
async def test_git_errors_are_translated(
    client: httpx.AsyncClient, kind: str, status: int, code: ErrorCode
) -> None:
    response = await client.get(f"/git/{kind}")
    assert (response.status_code, response.json()["code"]) == (status, code.value)


async def test_framework_errors_use_the_same_shape(client: httpx.AsyncClient) -> None:
    invalid = await client.post("/validate", json={"replicas": "many"})
    assert invalid.status_code == 422
    assert invalid.json()["details"]["errors"][0]["loc"] == ["body", "replicas"]
    missing = await client.get("/no-such-route")
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")


async def test_unexpected_errors_hide_internals_and_mint_a_request_id(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/boom", headers={"x-request-id": "bad id with spaces"})
    body = response.json()
    assert response.status_code == 500
    assert "secret internals" not in response.text
    assert body["request_id"].startswith("req_")
    assert response.headers["x-request-id"] == body["request_id"]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (FeatureDisabled("status is off"), 501, "FEATURE_DISABLED"),
        (DependencyUnavailable("hub down"), 502, "DEPENDENCY_UNAVAILABLE"),
        (NodeNotInCluster("moved"), 409, "NODE_NOT_IN_CLUSTER"),
        (UninstallAlreadyRunning("running"), 409, "UNINSTALL_ALREADY_RUNNING"),
        (UpgradeAlreadyRunning("running"), 409, "UPGRADE_ALREADY_RUNNING"),
        (UpgradeDecisionRefused("not now"), 409, "UPGRADE_DECISION_REFUSED"),
        (UpgradeTargetsRefused("no rules"), 409, "UPGRADE_TARGETS_REFUSED"),
        (AddServerAlreadyRunning("running"), 409, "ADD_SERVER_ALREADY_RUNNING"),
        (JobAlreadyRunning("unfinished"), 409, "JOB_ALREADY_RUNNING"),
    ],
)
async def test_non_git_errors_have_their_own_codes(error: AppError, status: int, code: str) -> None:
    app = make_app()

    @app.get("/dependency")
    async def dependency() -> None:
        raise error

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/dependency")
    assert (response.status_code, response.json()["code"]) == (status, code)
    assert response.json()["type"] == f"/problems/{code.lower().replace('_', '-')}"


class HubDown(Exception):
    """A service's own error, as day1's and day2's domains define them."""


async def test_a_services_own_errors_take_the_app_error_path_and_a_5xx_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = make_app()
    register_domain_errors(app, HubDown, lambda exc: DependencyUnavailable(f"hub: {exc}"))

    @app.get("/hub")
    async def hub() -> None:
        raise HubDown("timed out")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with caplog.at_level(logging.WARNING, logger="wingman_core.web.exception_handlers"):
            response = await client.get("/hub")
    assert (response.status_code, response.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    assert response.json()["detail"] == "hub: timed out"
    assert "DEPENDENCY_UNAVAILABLE on /hub: hub: timed out" in caplog.text
