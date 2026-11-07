"""Session tokens, roles and the auth dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from fastapi import FastAPI
from prometheus_client import CollectorRegistry
from pydantic import SecretStr, ValidationError

from wingman_core.domain.users import Role, User, resolve_role
from wingman_core.infrastructure.session_tokens import InvalidSessionError, SessionTokens
from wingman_core.observability.metrics import WingmanMetrics
from wingman_core.settings import AuthSettings
from wingman_core.web.app_factory import create_base_app
from wingman_core.web.auth import AdminUser, CurrentUser

SECRET = "s" * 40
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
ADMIN = User("jane", Role.ADMIN, groups=("wingman-admins",), uid="u1", full_name="Jane")
VIEWER = User("bob", Role.VIEWER, groups=("wingman-viewers",))


def tokens(now: datetime = NOW) -> SessionTokens:
    return SessionTokens(SECRET, ttl=timedelta(hours=8), clock=lambda: now)


@pytest.mark.parametrize(
    ("groups", "role"),
    [
        (["wingman-admins", "wingman-viewers"], Role.ADMIN),
        (["wingman-viewers"], Role.VIEWER),
        (["someone-else"], None),
        ([], None),
    ],
)
def test_role_resolution_admin_wins(groups: list[str], role: Role | None) -> None:
    resolved = resolve_role(
        groups, admin_groups=["wingman-admins"], viewer_groups=["wingman-viewers"]
    )
    assert resolved is role


def test_token_round_trip_keeps_identity_and_role() -> None:
    assert tokens().verify(tokens().issue(ADMIN)) == ADMIN


def test_expired_token_is_refused() -> None:
    old = tokens(NOW - timedelta(hours=9)).issue(VIEWER)
    with pytest.raises(InvalidSessionError):
        tokens().verify(old)


def test_expiry_follows_the_injected_clock_not_the_wall_clock() -> None:
    """A fixed clock far in the past still verifies its own fresh tokens."""
    past = datetime(2001, 1, 1, tzinfo=UTC)
    assert tokens(past).verify(tokens(past).issue(VIEWER)) == VIEWER
    with pytest.raises(InvalidSessionError, match="expired"):
        tokens(past + timedelta(hours=8)).verify(tokens(past).issue(VIEWER))


def test_a_token_issued_in_the_future_is_refused_beyond_the_skew() -> None:
    assert tokens().verify(tokens(NOW + timedelta(seconds=20)).issue(VIEWER)) == VIEWER
    with pytest.raises(InvalidSessionError, match="future"):
        tokens().verify(tokens(NOW + timedelta(minutes=5)).issue(VIEWER))


def test_a_token_with_non_numeric_times_is_refused() -> None:
    token = jwt.encode({"sub": "x", "role": "admin", "iat": "now", "exp": "later"}, SECRET)
    with pytest.raises(InvalidSessionError, match="non-numeric"):
        tokens().verify(token)


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        jwt.encode(
            {"sub": "x", "role": "admin", "iat": NOW, "exp": NOW + timedelta(days=999)},
            "other" * 10,
        ),
        jwt.encode(
            {"sub": "x", "role": "root", "iat": NOW, "exp": NOW + timedelta(days=999)}, SECRET
        ),
        jwt.encode(
            {"sub": "", "role": "admin", "iat": NOW, "exp": NOW + timedelta(days=999)}, SECRET
        ),
        jwt.encode({"sub": "x", "iat": NOW, "exp": NOW + timedelta(days=999)}, SECRET),
    ],
    ids=["garbage", "wrong-secret", "unknown-role", "empty-subject", "no-role"],
)
def test_bad_tokens_are_refused(token: str) -> None:
    with pytest.raises(InvalidSessionError):
        SessionTokens(SECRET, ttl=timedelta(hours=8)).verify(token)


def test_auth_settings_refuse_a_short_secret_and_split_groups() -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        AuthSettings(jwt_secret_key=SecretStr("short"))
    settings = AuthSettings(
        jwt_secret_key=SecretStr(SECRET), wingman_admin_groups=" a, b ,", wingman_viewer_groups=""
    )
    assert settings.admin_groups == ("a", "b")
    assert settings.viewer_groups == ()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    session = SessionTokens(SECRET, ttl=timedelta(hours=8))
    metrics = WingmanMetrics(CollectorRegistry(), component="t", version="0", commit="0")
    app: FastAPI = create_base_app(title="t", version="0", metrics=metrics, session_tokens=session)

    @app.get("/read")
    async def read(user: CurrentUser) -> dict[str, str]:
        return {"user": user.username}

    @app.post("/write")
    async def write(user: AdminUser) -> dict[str, str]:
        return {"user": user.username}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        c.headers["x-test-admin"] = session.issue(ADMIN)
        c.headers["x-test-viewer"] = session.issue(VIEWER)
        yield c


async def test_dependencies_enforce_login_and_role(client: httpx.AsyncClient) -> None:
    admin = {"authorization": f"Bearer {client.headers['x-test-admin']}"}
    viewer = {"authorization": f"Bearer {client.headers['x-test-viewer']}"}
    assert (await client.get("/read", headers=viewer)).json() == {"user": "bob"}
    assert (await client.post("/write", headers=admin)).json() == {"user": "jane"}
    forbidden = await client.post("/write", headers=viewer)
    assert (forbidden.status_code, forbidden.json()["code"]) == (403, "FORBIDDEN")
    for headers in ({}, {"authorization": "Basic abc"}, {"authorization": "Bearer nope"}):
        response = await client.get("/read", headers=headers)
        assert (response.status_code, response.json()["code"]) == (401, "UNAUTHORIZED")
