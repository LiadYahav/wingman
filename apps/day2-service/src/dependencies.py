"""FastAPI dependency providers for Day2 Service."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from wingman_shared.auth.jwt import JWTManager
from wingman_shared.cache import CacheManager
from wingman_shared.exceptions import AuthError
from wingman_shared.gitlab_client import GitLabGroupClient
from wingman_shared.models import UserInfo
from wingman_shared.path_resolver import PathResolver

from .config import Settings, get_settings
from .services.addon_service import AddonService
from .services.approval_service import ApprovalService
from .services.audit_service import AuditService

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/callback")


# ── Infrastructure singletons ─────────────────────────────────────────────────


@lru_cache
def get_sigs_group_client() -> GitLabGroupClient:
    """Returns a GitLabGroupClient for the sigs subgroup.

    Teams inside sigs are separate GitLab projects; this client enumerates them
    and hands out per-team GitLabClient instances.
    """
    settings = get_settings()
    return GitLabGroupClient(
        gitlab_url=settings.GITLAB_URL,
        access_token=settings.GITLAB_ACCESS_TOKEN,
        group_path=settings.day2_sigs_group_path,
        default_branch=settings.GITLAB_DEFAULT_BRANCH,
        ssl_verify=settings.gitlab_ssl_verify,
    )


@lru_cache
def get_path_resolver() -> PathResolver:
    settings = get_settings()
    return PathResolver(
        day1_clusters_path_template="",  # not used in day2 service
        day2_addon_defs_path_template=settings.DAY2_ADDON_DEFS_PATH_TEMPLATE,
        day2_addon_overrides_path_template=settings.DAY2_ADDON_OVERRIDES_PATH_TEMPLATE,
        specs_root_path="",
    )


@lru_cache
def get_cache() -> CacheManager:
    return CacheManager()


@lru_cache
def get_jwt_manager() -> JWTManager:
    settings = get_settings()
    return JWTManager(
        secret_key=settings.JWT_SECRET_KEY,
        expiry_hours=settings.JWT_EXPIRY_HOURS,
    )


# ── Auth dependency ────────────────────────────────────────────────────────────


async def get_current_user(
    token: Annotated[str, Depends(_oauth2_scheme)],
    jwt_manager: Annotated[JWTManager, Depends(get_jwt_manager)],
) -> UserInfo:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt_manager.validate_token(token)
        username: str = payload.get("sub", "")
        groups: list[str] = payload.get("groups", [])
        uid: str = payload.get("uid", "")
        role: str = payload.get("role", "viewer")
        if not username:
            raise credentials_exception
        return UserInfo(username=username, groups=groups, uid=uid, role=role)  # type: ignore[arg-type]
    except AuthError as exc:
        raise credentials_exception from exc


async def require_admin(user: Annotated[UserInfo, Depends(get_current_user)]) -> UserInfo:
    """Block viewer-role users from write operations."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires admin access. Viewers can only read data.",
        )
    return user


# ── Service factories ──────────────────────────────────────────────────────────


def get_addon_service(
    group_client: Annotated[GitLabGroupClient, Depends(get_sigs_group_client)],
    path_resolver: Annotated[PathResolver, Depends(get_path_resolver)],
    cache: Annotated[CacheManager, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AddonService:
    return AddonService(
        group_client=group_client,
        path_resolver=path_resolver,
        cache=cache,
        settings=settings,
    )


def get_approval_service(
    group_client: Annotated[GitLabGroupClient, Depends(get_sigs_group_client)],
    cache: Annotated[CacheManager, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApprovalService:
    return ApprovalService(
        group_client=group_client,
        cache=cache,
        cache_key_prefix="day2",
        cache_ttl=settings.CACHE_APPROVALS_TTL,
    )


def get_audit_service(
    group_client: Annotated[GitLabGroupClient, Depends(get_sigs_group_client)],
    cache: Annotated[CacheManager, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuditService:
    return AuditService(
        group_client=group_client,
        cache=cache,
        cache_ttl=settings.CACHE_AUDIT_TTL,
    )


# ── Convenience aliases ────────────────────────────────────────────────────────

CurrentUser = Annotated[UserInfo, Depends(get_current_user)]
AdminUser = Annotated[UserInfo, Depends(require_admin)]
AddonServiceDep = Annotated[AddonService, Depends(get_addon_service)]
ApprovalServiceDep = Annotated[ApprovalService, Depends(get_approval_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
