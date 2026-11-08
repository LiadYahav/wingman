"""``/api/auth``: login configuration, OAuth callback, dev login, who am I."""

from __future__ import annotations

from fastapi import APIRouter

from wingman_core.web.auth import CurrentUser
from wingman_day1.api.deps import Context
from wingman_day1.api.v1.schemas import AuthConfigOut, CallbackIn, DevLoginIn, SessionOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/config")
async def auth_config(context: Context) -> AuthConfigOut:
    """Where the login page sends the browser, and whether dev login is on."""
    config = await context.auth.config()
    return AuthConfigOut(
        authorize_url=config.authorize_url, dev_auth_enabled=config.dev_auth_enabled
    )


@router.post("/callback")
async def auth_callback(body: CallbackIn, context: Context) -> SessionOut:
    """Exchange the OpenShift OAuth code for a Wingman session (401/403 when refused)."""
    session = await context.auth.oauth_login(body.code)
    return SessionOut(access_token=session.token, user=UserOut.of(session.user))


@router.post("/dev-login")
async def dev_login(body: DevLoginIn, context: Context) -> SessionOut:
    """A session without OpenShift; 404 unless dev login is enabled, 401 on a wrong secret."""
    session = context.auth.dev_login(username=body.username, role=body.role, secret=body.secret)
    return SessionOut(access_token=session.token, user=UserOut.of(session.user))


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    """The user the session token was issued for."""
    return UserOut.of(user)
