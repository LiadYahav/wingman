"""Auth routes — OpenShift OAuth callback and user info.

Login enforces group-based access control:
- User must be in at least one group from WINGMAN_ADMIN_GROUPS or WINGMAN_VIEWER_GROUPS
- Role is resolved at login and stored in the JWT
- Subsequent requests validate the JWT and read the role from it
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from wingman_shared.auth.jwt import JWTManager
from wingman_shared.auth.openshift_oauth import OpenShiftOAuth
from wingman_shared.auth.rbac import get_user_role, parse_groups_env
from wingman_shared.exceptions import AuthError
from wingman_shared.models import UserInfo

from ..config import Settings, get_settings
from ..dependencies import CurrentUser, get_jwt_manager, get_oauth_client

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthCallbackRequest(BaseModel):
    code: str


class AuthCallbackResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class AuthConfigResponse(BaseModel):
    authorize_url: str
    dev_auth_enabled: bool = False


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config(
    settings: Annotated[Settings, Depends(get_settings)],
    oauth: Annotated[OpenShiftOAuth, Depends(get_oauth_client)],
) -> AuthConfigResponse:
    """Return the OAuth config for the frontend."""
    if settings.DEV_AUTH_ENABLED:
        return AuthConfigResponse(authorize_url="", dev_auth_enabled=True)
    url = await oauth.get_authorize_url()
    return AuthConfigResponse(authorize_url=url, dev_auth_enabled=False)


@router.post("/callback", response_model=AuthCallbackResponse)
async def auth_callback(
    body: AuthCallbackRequest,
    oauth: Annotated[OpenShiftOAuth, Depends(get_oauth_client)],
    jwt_manager: Annotated[JWTManager, Depends(get_jwt_manager)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthCallbackResponse:
    """Exchange OpenShift OAuth code for a platform JWT.

    Enforces group-based access control:
    - Only users in WINGMAN_ADMIN_GROUPS or WINGMAN_VIEWER_GROUPS can log in
    - Role is embedded in the JWT for subsequent authorization
    """
    try:
        opaque_token = await oauth.exchange_code(body.code)
        user_info = await oauth.get_user_info(opaque_token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    admin_groups = parse_groups_env(settings.WINGMAN_ADMIN_GROUPS)
    viewer_groups = parse_groups_env(settings.WINGMAN_VIEWER_GROUPS)

    provisional_user = UserInfo(
        username=user_info["username"],
        groups=user_info["groups"],
        uid=user_info["uid"],
        full_name=user_info.get("full_name", ""),
    )

    # Enforce group membership — deny login if not in any allowed group
    role = get_user_role(provisional_user, admin_groups, viewer_groups)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Access denied. User '{provisional_user.username}' is not a member of any "
                f"allowed group. Contact your administrator."
            ),
        )

    user = provisional_user.model_copy(update={"role": role.value})
    token = jwt_manager.create_token(
        username=user.username,
        groups=user.groups,
        uid=user.uid,
        role=role.value,
    )
    return AuthCallbackResponse(access_token=token, user=user)


@router.get("/me", response_model=UserInfo)
async def get_me(user: CurrentUser) -> UserInfo:
    """Return current user info from the JWT."""
    return user


# ── Dev auth (local/minikube testing only) ─────────────────────────────────────


class DevLoginRequest(BaseModel):
    username: str
    role: str = "admin"  # "admin" or "viewer"
    secret: str = ""


@router.post("/dev-login", response_model=AuthCallbackResponse)
async def dev_login(
    body: DevLoginRequest,
    jwt_manager: Annotated[JWTManager, Depends(get_jwt_manager)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthCallbackResponse:
    """Issue a JWT without OpenShift OAuth — for local/minikube testing ONLY.

    Requires DEV_AUTH_ENABLED=true and a matching DEV_AUTH_SECRET in config.
    Never expose this endpoint in production.
    """
    if not settings.DEV_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",  # deliberately vague — don't advertise this endpoint
        )
    # Secret check only applies when a secret is configured
    if settings.DEV_AUTH_SECRET and body.secret != settings.DEV_AUTH_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret")
    if body.role not in ("admin", "viewer"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="role must be admin or viewer"
        )

    admin_groups = ["wingman-admins"] if body.role == "admin" else []
    viewer_groups = ["wingman-viewers"] if body.role == "viewer" else []

    user = UserInfo(
        username=body.username,
        groups=admin_groups + viewer_groups,
        uid=f"dev-{body.username}",
        full_name=f"Dev User ({body.username})",
        role=body.role,
    )
    token = jwt_manager.create_token(
        username=user.username,
        groups=user.groups,
        uid=user.uid,
        role=body.role,
    )
    return AuthCallbackResponse(access_token=token, user=user)
