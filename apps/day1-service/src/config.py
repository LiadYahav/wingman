"""Day1 Service configuration — all values from environment variables.

All GitLab paths use template strings with placeholders ({site}, {mce}, {cluster}).
No paths are hardcoded.
"""

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
    SERVICE_PORT: int = 8001
    LOG_LEVEL: str = "INFO"

    # ── GitLab connection ─────────────────────────────────────────────────────
    GITLAB_URL: str = Field(description="GitLab instance URL")
    GITLAB_ACCESS_TOKEN: str = Field(description="GitLab personal/project access token")

    # Accepts numeric ID (42) or path string ("group/subgroup/project")
    DAY1_GITLAB_PROJECT_ID: str = Field(description="Day1 GitLab project ID or path")
    SPECS_GITLAB_PROJECT_ID: str = Field(description="Cluster specs GitLab project ID or path")

    GITLAB_DEFAULT_BRANCH: str = "main"

    # TLS verification: "true"/"false" or a path to a CA bundle file
    GITLAB_SSL_VERIFY: str = "true"

    # ── Day1 path templates (inside the Day1 project) ─────────────────────────
    # Placeholders: {site}, {mce}  (cluster name used as filename, not a dir)
    DAY1_CLUSTERS_PATH_TEMPLATE: str = "sites/{site}/mces/{mce}/hostedClusters"
    DAY1_CLUSTER_FILE_SUFFIX: str = ".yaml"

    # ── Specs path templates (inside the Specs project) ──────────────────────
    # Specs live at {SPECS_ROOT_PATH}/{spec_name}.yaml
    SPECS_ROOT_PATH: str = "specs"

    # ── OpenShift OAuth ───────────────────────────────────────────────────────
    # Leave empty when DEV_AUTH_ENABLED=true
    OPENSHIFT_OAUTH_HOST: str = Field(default="", description="OAuth server hostname")
    OPENSHIFT_API_HOST: str = Field(default="", description="Kubernetes API server host:port")
    OPENSHIFT_OAUTH_CLIENT_ID: str = Field(default="", description="OAuthClient metadata.name")
    OPENSHIFT_OAUTH_CLIENT_SECRET: str = Field(default="", description="OAuthClient secret")
    OPENSHIFT_OAUTH_REDIRECT_URI: str = Field(
        default="", description="Must match OAuthClient redirectURIs"
    )
    OPENSHIFT_SSL_VERIFY: str = Field(
        default="false",
        description="SSL verification for OpenShift API/OAuth calls: 'true', 'false', or CA bundle path",
    )

    # ── Dev auth (local/minikube testing only — never enable in production) ────
    # When true, /api/auth/dev-login bypasses OpenShift OAuth entirely.
    DEV_AUTH_ENABLED: bool = Field(
        default=False,
        description="Enable simple dev login (NO OpenShift OAuth). For local testing only.",
    )
    DEV_AUTH_SECRET: str = Field(
        default="",
        description="Secret required by the dev login endpoint. Set to a non-empty value.",
    )

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = Field(description="Secret key for signing platform JWTs")
    JWT_EXPIRY_HOURS: int = 8

    # ── GitLab Webhook ────────────────────────────────────────────────────────
    GITLAB_WEBHOOK_SECRET: str = Field(
        default="", description="Secret token to verify GitLab webhook payloads"
    )

    # ── Group-based access control ────────────────────────────────────────────
    # Comma-separated OpenShift group names. Users must be in at least one group.
    # Admin groups: full create/modify/delete/approve access
    WINGMAN_ADMIN_GROUPS: str = Field(
        default="wingman-admins",
        description="Comma-separated OpenShift groups that grant admin access",
    )
    # Viewer groups: read-only access (optional — leave empty to disable viewer role)
    WINGMAN_VIEWER_GROUPS: str = Field(
        default="",
        description="Comma-separated OpenShift groups that grant read-only viewer access",
    )

    # ── Day2 service URL (for inter-service calls) ────────────────────────────
    DAY2_SERVICE_URL: str = "http://wingman-day2:8002"

    # ── Live cluster status (OpenShift/HyperShift API) ────────────────────────
    # Disabled by default; requires MCE SA tokens and cannot run on minikube.
    CLUSTER_STATUS_ENABLED: bool = Field(
        default=False,
        description="Enable live HostedCluster/NodePool status checks via MCE API",
    )
    MCE_API_DOMAIN: str = Field(
        default="",
        description="Base domain for MCE API servers. URL: https://api.{mce}.{domain}:6443",
    )
    # Path to a file containing MCE SA tokens (YAML: {mce-name: token})
    MCE_TOKENS_FILE: str = Field(
        default="/etc/wingman/mce-tokens/tokens",
        description="Path to mounted file with MCE SA tokens",
    )
    MCE_CLUSTER_NAME_PREFIX: str = Field(
        default="ocp4-",
        description=(
            "Prefix stripped from cluster names to derive HostedCluster CR names "
            "and NodePool namespaces (hcp-{name})"
        ),
    )
    MCE_SSL_VERIFY: str = Field(
        default="false",
        description="SSL verification for MCE API calls: true/false or CA bundle path",
    )

    # ── Cache TTLs (seconds) ─────────────────────────────────────────────────
    # Longer TTLs reduce GitLab API calls; frontend staleTime handles freshness
    CACHE_CLUSTER_LIST_TTL: float = 180.0  # 3 min
    CACHE_CLUSTER_DETAIL_TTL: float = 180.0  # 3 min
    CACHE_SPEC_LIST_TTL: float = 300.0  # 5 min
    CACHE_SPEC_DETAIL_TTL: float = 300.0  # 5 min
    CACHE_APPROVALS_TTL: float = 120.0  # 2 min
    CACHE_AUDIT_TTL: float = 300.0  # 5 min
    CACHE_BACKGROUND_REFRESH_SECONDS: float = 120.0  # 2 min

    @property
    def mce_ssl_verify(self) -> bool | str:
        """Parse MCE_SSL_VERIFY: True, False, or CA bundle path."""
        if self.MCE_SSL_VERIFY.lower() == "true":
            return True
        if self.MCE_SSL_VERIFY.lower() == "false":
            return False
        return self.MCE_SSL_VERIFY

    @property
    def openshift_ssl_verify(self) -> bool | str:
        """Parse OPENSHIFT_SSL_VERIFY: True, False, or CA bundle path."""
        if self.OPENSHIFT_SSL_VERIFY.lower() == "true":
            return True
        if self.OPENSHIFT_SSL_VERIFY.lower() == "false":
            return False
        return self.OPENSHIFT_SSL_VERIFY

    @property
    def gitlab_ssl_verify(self) -> bool | str:
        """Return parsed SSL verify setting: True, False, or CA bundle path."""
        if self.GITLAB_SSL_VERIFY.lower() == "true":
            return True
        if self.GITLAB_SSL_VERIFY.lower() == "false":
            return False
        return self.GITLAB_SSL_VERIFY  # treat as path to CA bundle

    @property
    def day1_project_id(self) -> int | str:
        """Day1 project ID as int if numeric, else string path."""
        try:
            return int(self.DAY1_GITLAB_PROJECT_ID)
        except ValueError:
            return self.DAY1_GITLAB_PROJECT_ID

    @property
    def specs_project_id(self) -> int | str:
        try:
            return int(self.SPECS_GITLAB_PROJECT_ID)
        except ValueError:
            return self.SPECS_GITLAB_PROJECT_ID


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
