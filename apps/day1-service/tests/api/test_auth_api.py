"""``/api/auth``: config, OAuth callback, dev login and ``/me`` over HTTP."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons

OAUTH = {
    "dev_auth_enabled": False,
    "openshift_api_host": "api.mgmt.example.invalid:6443",
    "openshift_oauth_client_id": "wingman",
    "openshift_oauth_client_secret": "client-secret",
    "openshift_oauth_redirect_uri": "https://wingman.example.invalid/login",
}


@pytest.fixture
def oauth_app(support: Any, gitlab: Any, hub: Any, identity: Any, clock: Any) -> FastAPI:
    return support.build_app(
        gitlab=gitlab, hub=hub, identity=identity, day2=FakeDay2Addons(), clock=clock, **OAUTH
    )


@pytest.fixture
async def oauth_client(oauth_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=oauth_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as c:
        yield c


async def test_config_with_dev_login_on(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/auth/config")
    assert response.json() == {"authorize_url": "", "dev_auth_enabled": True}


async def test_config_with_oauth_points_at_the_authorize_url(
    oauth_client: httpx.AsyncClient,
) -> None:
    response = await oauth_client.get("/api/auth/config")
    assert response.json() == {
        "authorize_url": "https://oauth.example.invalid/oauth/authorize?client_id=wingman",
        "dev_auth_enabled": False,
    }


@pytest.mark.parametrize(
    ("code", "username", "role"),
    [("code-admin", "olga", "admin"), ("code-viewer", "vic", "viewer")],
)
async def test_the_callback_gives_a_session_with_the_groups_role(
    oauth_client: httpx.AsyncClient, code: str, username: str, role: str
) -> None:
    response = await oauth_client.post("/api/auth/callback", json={"code": code})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert (body["user"]["username"], body["user"]["role"]) == (username, role)
    me = await oauth_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.json()["username"] == username
    clusters = await oauth_client.get(
        "/api/day1/clusters", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert clusters.status_code == 200


async def test_an_unknown_code_is_unauthorized(oauth_client: httpx.AsyncClient) -> None:
    response = await oauth_client.post("/api/auth/callback", json={"code": "forged"})
    assert (response.status_code, response.json()["code"]) == (401, "UNAUTHORIZED")


async def test_someone_in_no_wingman_group_is_forbidden(oauth_client: httpx.AsyncClient) -> None:
    response = await oauth_client.post("/api/auth/callback", json={"code": "code-nobody"})
    assert (response.status_code, response.json()["code"]) == (403, "FORBIDDEN")
    assert "nora" in response.json()["detail"]


async def test_dev_login_with_the_secret(client: httpx.AsyncClient, support: Any) -> None:
    response = await client.post(
        "/api/auth/dev-login",
        json={"username": "dev", "role": "admin", "secret": support.DEV_SECRET},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"] == {
        "username": "dev",
        "groups": ["wingman-dev-admins"],
        "uid": "dev-dev",
        "full_name": "Dev User (dev)",
        "role": "admin",
    }
    me = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.json()["role"] == "admin"


async def test_dev_login_without_the_secret_is_unauthorized(client: httpx.AsyncClient) -> None:
    # Legacy: with DEV_AUTH_SECRET empty, dev login minted an admin token for anyone;
    # the web app never sent the secret at all.
    response = await client.post("/api/auth/dev-login", json={"username": "dev", "role": "admin"})
    assert (response.status_code, response.json()["code"]) == (401, "UNAUTHORIZED")


async def test_dev_login_with_a_bad_role_is_invalid(
    client: httpx.AsyncClient, support: Any
) -> None:
    response = await client.post(
        "/api/auth/dev-login",
        json={"username": "dev", "role": "root", "secret": support.DEV_SECRET},
    )
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")


async def test_dev_login_does_not_exist_when_disabled(
    oauth_client: httpx.AsyncClient, support: Any
) -> None:
    response = await oauth_client.post(
        "/api/auth/dev-login",
        json={"username": "dev", "role": "admin", "secret": support.DEV_SECRET},
    )
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")


async def test_me_needs_a_session(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/auth/me")
    assert (response.status_code, response.json()["code"]) == (401, "UNAUTHORIZED")


async def test_a_callback_body_with_extra_fields_is_refused(
    oauth_client: httpx.AsyncClient,
) -> None:
    response = await oauth_client.post(
        "/api/auth/callback", json={"code": "code-admin", "state": "x"}
    )
    assert response.status_code == 422
