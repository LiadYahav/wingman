"""FastAPI dependency providers for Day1 Service.

All singleton resources are created once at startup and injected via Depends().
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from wingman_shared.auth.jwt import JWTManager
from wingman_shared.auth.openshift_oauth import OpenShiftOAuth
from wingman_shared.cache import CacheManager
from wingman_shared.exceptions import AuthError
from wingman_shared.gitlab_client import GitLabClient
from wingman_shared.models import UserInfo
from wingman_shared.path_resolver import PathResolver

from .config import Settings, get_settings
from .services.approval_service import ApprovalService
from .services.audit_service import AuditService
from .services.cluster_service import ClusterService
from .services.cluster_status_service import ClusterStatusService
from .services.drift_detector import DriftDetector
from .services.spec_service import SpecService

# Declares where the Bearer token comes from (informational for OpenAPI docs)
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/callback")


# ── Infrastructure singletons ─────────────────────────────────────────────────
# Note: call get_settings() directly (no Depends) so @lru_cache can hash args.
# get_settings() itself is @lru_cache so Settings is created only once.


@lru_cache
def get_gitlab_day1() -> GitLabClient:
    settings = get_settings()
    return GitLabClient(
        gitlab_url=settings.GITLAB_URL,
        access_token=settings.GITLAB_ACCESS_TOKEN,
        project_id=settings.day1_project_id,
        default_branch=settings.GITLAB_DEFAULT_BRANCH,
        ssl_verify=settings.gitlab_ssl_verify,
    )


@lru_cache
def get_gitlab_specs() -> GitLabClient:
    settings = get_settings()
    return GitLabClient(
        gitlab_url=settings.GITLAB_URL,
        access_token=settings.GITLAB_ACCESS_TOKEN,
        project_id=settings.specs_project_id,
        default_branch=settings.GITLAB_DEFAULT_BRANCH,
        ssl_verify=settings.gitlab_ssl_verify,
    )


@lru_cache
def get_path_resolver() -> PathResolver:
    settings = get_settings()
    return PathResolver(
        day1_clusters_path_template=settings.DAY1_CLUSTERS_PATH_TEMPLATE,
        day2_addon_defs_path_template="",  # not used in day1 service
        day2_addon_overrides_path_template="",
        day2_teams_root_path="",
        specs_root_path=settings.SPECS_ROOT_PATH,
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


@lru_cache
def get_oauth_client() -> OpenShiftOAuth:
    settings = get_settings()
    return OpenShiftOAuth(
        oauth_host=settings.OPENSHIFT_OAUTH_HOST,
        api_host=settings.OPENSHIFT_API_HOST,
        client_id=settings.OPENSHIFT_OAUTH_CLIENT_ID,
        client_secret=settings.OPENSHIFT_OAUTH_CLIENT_SECRET,
        redirect_uri=settings.OPENSHIFT_OAUTH_REDIRECT_URI,
        ssl_verify=settings.openshift_ssl_verify,
    )


# ── Auth dependency ────────────────────────────────────────────────────────────


async def get_current_user(
    token: Annotated[str, Depends(_oauth2_scheme)],
    jwt_manager: Annotated[JWTManager, Depends(get_jwt_manager)],
) -> UserInfo:
    """Validate Bearer JWT and return the current UserInfo (with role)."""
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
    """Dependency that blocks viewer-role users from write operations."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires admin access. Viewers can only read data.",
        )
    return user


# ── Service factories (one per request — lightweight, no I/O at construction) ─


def get_cluster_service(
    gl_day1: Annotated[GitLabClient, Depends(get_gitlab_day1)],
    path_resolver: Annotated[PathResolver, Depends(get_path_resolver)],
    cache: Annotated[CacheManager, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ClusterService:
    return ClusterService(
        gitlab_day1=gl_day1,
        path_resolver=path_resolver,
        cache=cache,
        default_branch=settings.GITLAB_DEFAULT_BRANCH,
        cluster_file_suffix=settings.DAY1_CLUSTER_FILE_SUFFIX,
    )


def get_spec_service(
    gl_specs: Annotated[GitLabClient, Depends(get_gitlab_specs)],
    path_resolver: Annotated[PathResolver, Depends(get_path_resolver)],
    cache: Annotated[CacheManager, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SpecService:
    return SpecService(
        gitlab_specs=gl_specs,
        path_resolver=path_resolver,
        cache=cache,
        default_branch=settings.GITLAB_DEFAULT_BRANCH,
    )


def get_approval_service(
    gl_day1: Annotated[GitLabClient, Depends(get_gitlab_day1)],
    cache: Annotated[CacheManager, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApprovalService:
    return ApprovalService(
        gitlab_client=gl_day1,
        cache=cache,
        cache_key_prefix="day1",
        cache_ttl=settings.CACHE_APPROVALS_TTL,
    )


def get_drift_detector(
    gl_day1: Annotated[GitLabClient, Depends(get_gitlab_day1)],
    gl_specs: Annotated[GitLabClient, Depends(get_gitlab_specs)],
    path_resolver: Annotated[PathResolver, Depends(get_path_resolver)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DriftDetector:
    return DriftDetector(
        gitlab_day1=gl_day1,
        gitlab_specs=gl_specs,
        path_resolver=path_resolver,
        default_branch=settings.GITLAB_DEFAULT_BRANCH,
    )


@lru_cache
def get_cluster_status_service() -> ClusterStatusService | None:
    """Return a ClusterStatusService if the feature is enabled, else None."""
    settings = get_settings()
    if not settings.CLUSTER_STATUS_ENABLED:
        return None

    import logging  # noqa: PLC0415

    import yaml  # noqa: PLC0415

    _logger = logging.getLogger(__name__)
    try:
        with open(settings.MCE_TOKENS_FILE) as f:
            tokens: dict[str, str] = yaml.safe_load(f) or {}
    except Exception as exc:
        _logger.error("Cannot load MCE tokens from %s: %s", settings.MCE_TOKENS_FILE, exc)
        tokens = {}

    return ClusterStatusService(
        mce_tokens=tokens,
        mce_api_domain=settings.MCE_API_DOMAIN,
        ssl_verify=settings.mce_ssl_verify,
        cluster_name_prefix=settings.MCE_CLUSTER_NAME_PREFIX,
    )


def get_audit_service(
    gl_day1: Annotated[GitLabClient, Depends(get_gitlab_day1)],
    gl_specs: Annotated[GitLabClient, Depends(get_gitlab_specs)],
    cache: Annotated[CacheManager, Depends(get_cache)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuditService:
    return AuditService(
        gitlab_day1=gl_day1,
        gitlab_specs=gl_specs,
        cache=cache,
        cache_ttl=settings.CACHE_AUDIT_TTL,
    )


# ── Convenience type aliases for route handlers ────────────────────────────────

CurrentUser = Annotated[UserInfo, Depends(get_current_user)]
AdminUser = Annotated[UserInfo, Depends(require_admin)]  # use on all write endpoints
ClusterServiceDep = Annotated[ClusterService, Depends(get_cluster_service)]
DriftDetectorDep = Annotated[DriftDetector, Depends(get_drift_detector)]
SpecServiceDep = Annotated[SpecService, Depends(get_spec_service)]
ApprovalServiceDep = Annotated[ApprovalService, Depends(get_approval_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
