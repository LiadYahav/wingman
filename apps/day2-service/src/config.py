"""Day2 Service configuration — all values from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Service ───────────────────────────────────────────────────────────────
    SERVICE_PORT: int = 8002
    LOG_LEVEL: str = "INFO"

    # ── GitLab connection ─────────────────────────────────────────────────────
    GITLAB_URL: str = Field(description="GitLab instance URL")
    GITLAB_ACCESS_TOKEN: str = Field(description="GitLab personal/project access token")
    DAY2_SIGS_GROUP_PATH: str = Field(
        description="GitLab group path for the sigs subgroup (e.g. wingman-dev/sigs)"
    )
    GITLAB_DEFAULT_BRANCH: str = "main"
    GITLAB_SSL_VERIFY: str = "true"

    # ── Day2 path templates (relative to each team's GitLab project root) ─────
    # Teams are separate GitLab projects inside DAY2_SIGS_GROUP_PATH.
    # Placeholders: {addon}
    DAY2_ADDON_DEFS_PATH_TEMPLATE: str = "operators/{addon}"
    # Placeholders: {mce}, {cluster}, {addon}
    DAY2_ADDON_OVERRIDES_PATH_TEMPLATE: str = "mces/{mce}/{cluster}/{addon}"

    # ── JWT validation (same secret as day1) ─────────────────────────────────
    JWT_SECRET_KEY: str = Field(description="Secret key for validating platform JWTs")
    JWT_EXPIRY_HOURS: int = 8

    # ── Group-based access control (must match day1 config) ───────────────────
    WINGMAN_ADMIN_GROUPS: str = Field(
        default="wingman-admins",
        description="Comma-separated OpenShift groups that grant admin access",
    )
    WINGMAN_VIEWER_GROUPS: str = Field(
        default="",
        description="Comma-separated OpenShift groups that grant read-only viewer access",
    )

    # ── Cache TTLs (seconds) ─────────────────────────────────────────────────
    # Longer TTLs reduce GitLab API calls; frontend staleTime handles freshness
    CACHE_ADDON_CATALOG_TTL: float = 300.0  # 5 min
    CACHE_ADDON_VALUES_TTL: float = 300.0  # 5 min
    CACHE_HELM_VALUES_TTL: float = 600.0  # 10 min (helm charts change infrequently)
    CACHE_HELM_BRANCHES_TTL: float = 300.0  # 5 min
    CACHE_APPROVALS_TTL: float = 120.0  # 2 min
    CACHE_AUDIT_TTL: float = 300.0  # 5 min
    CACHE_BACKGROUND_REFRESH_SECONDS: float = 120.0  # 2 min

    @property
    def gitlab_ssl_verify(self) -> bool | str:
        if self.GITLAB_SSL_VERIFY.lower() == "true":
            return True
        if self.GITLAB_SSL_VERIFY.lower() == "false":
            return False
        return self.GITLAB_SSL_VERIFY

    @property
    def day2_sigs_group_path(self) -> str:
        return self.DAY2_SIGS_GROUP_PATH


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
