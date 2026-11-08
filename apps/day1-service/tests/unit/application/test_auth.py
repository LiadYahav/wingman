"""Login: OAuth codes become sessions by group; dev login needs the secret."""

from __future__ import annotations

from typing import Any

import pytest

from wingman_core.domain.users import Role
from wingman_core.infrastructure.session_tokens import SessionTokens
from wingman_day1.api.deps import Day1Context
from wingman_day1.domain.errors import (
    IdentityError,
    InvalidInputError,
    LoginRefusedError,
    ResourceNotFoundError,
)
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons


async def test_with_dev_login_on_there_is_no_oauth_redirect(context: Day1Context) -> None:
    config = await context.auth.config()
    assert (config.authorize_url, config.dev_auth_enabled) == ("", True)


async def test_an_admin_group_member_gets_an_admin_session(app: Any, context: Day1Context) -> None:
    session = await context.auth.oauth_login("code-admin")
    assert (session.user.username, session.user.role) == ("olga", Role.ADMIN)
    tokens: SessionTokens = app.state.session_tokens
    assert tokens.verify(session.token).username == "olga"


async def test_a_viewer_group_member_gets_a_viewer_session(context: Day1Context) -> None:
    assert (await context.auth.oauth_login("code-viewer")).user.role is Role.VIEWER


async def test_someone_in_no_wingman_group_is_refused(context: Day1Context) -> None:
    with pytest.raises(LoginRefusedError, match="nora"):
        await context.auth.oauth_login("code-nobody")


async def test_an_unknown_code_is_refused(context: Day1Context) -> None:
    with pytest.raises(IdentityError):
        await context.auth.oauth_login("forged")


async def test_without_oauth_configured_a_callback_is_refused(
    support: Any, gitlab: Any, hub: Any, clock: Any
) -> None:
    app = support.build_app(
        gitlab=gitlab, hub=hub, identity=None, day2=FakeDay2Addons(), clock=clock
    )
    context: Day1Context = app.state.day1
    with pytest.raises(IdentityError, match="not configured"):
        await context.auth.oauth_login("code-admin")
    assert (await context.auth.config()).authorize_url == ""


async def test_dev_login_needs_the_secret(context: Day1Context, support: Any) -> None:
    with pytest.raises(IdentityError):
        context.auth.dev_login(username="dev", role="admin", secret="wrong")
    session = context.auth.dev_login(username="dev", role="viewer", secret=support.DEV_SECRET)
    assert (session.user.username, session.user.role) == ("dev", Role.VIEWER)
    assert session.user.groups == ("wingman-dev-viewers",)


@pytest.mark.parametrize(("username", "role"), [("Dev User", "admin"), ("dev", "root")])
async def test_dev_login_validates_username_and_role(
    context: Day1Context, support: Any, username: str, role: str
) -> None:
    with pytest.raises(InvalidInputError):
        context.auth.dev_login(username=username, role=role, secret=support.DEV_SECRET)


async def test_dev_login_does_not_exist_when_disabled(
    support: Any, gitlab: Any, hub: Any, identity: Any, clock: Any
) -> None:
    app = support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=identity,
        day2=FakeDay2Addons(),
        clock=clock,
        dev_auth_enabled=False,
        openshift_api_host="api.mgmt.example.invalid:6443",
        openshift_oauth_client_id="wingman",
        openshift_oauth_client_secret="client-secret",
        openshift_oauth_redirect_uri="https://wingman.example.invalid/login",
    )
    context: Day1Context = app.state.day1
    with pytest.raises(ResourceNotFoundError):
        context.auth.dev_login(username="dev", role="admin", secret=support.DEV_SECRET)
    config = await context.auth.config()
    assert config.dev_auth_enabled is False
    assert config.authorize_url.startswith("https://oauth.example.invalid/")
