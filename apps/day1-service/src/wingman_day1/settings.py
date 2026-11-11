"""Day1's settings: the only place day1 reads its environment.

The GitLab connection, session tokens and runtime come from
``wingman_core.settings``; this adds what only day1 needs. Environment
variable names are the legacy service's where the meaning is unchanged, so
the chart's ConfigMap keeps working. Settings fail closed (ADR-0009): a
configuration that would let anyone in, or let nobody in, refuses to start.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, Self
from urllib.parse import urlsplit

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from wingman_core.domain.git import RepoPath
from wingman_core.settings import Environment, RuntimeSettings

MIN_DEV_AUTH_SECRET_LENGTH: Final = 32


def tls_verify(value: str) -> bool | str:
    """``true``/``false``, or a path to a CA bundle (the legacy ``*_SSL_VERIFY`` format)."""
    lowered = value.strip().lower()
    if lowered in ("true", "1", "yes", ""):
        return True
    if lowered in ("false", "0", "no"):
        return False
    return value.strip()


class Day1Settings(BaseSettings):
    """Everything day1-specific. Environment variable names are the field names, upper-cased."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    # ── The two projects (numeric id or group/project path) ──────────────────
    day1_gitlab_project_id: str = Field(min_length=1)
    specs_gitlab_project_id: str = Field(min_length=1)
    specs_root_path: str = "specs"

    # ── How a cluster file name becomes the chart's clusterName (ADR-0015) ───
    # Production strips "ocp4-" (ocp4-prod-x-site1 in hcp-prod-x-site1);
    # the GitHub sandbox keeps the whole stem: set it to "" there. The chart
    # sets it from day1.clusterNameStripPrefix; the legacy MCE_CLUSTER_NAME_PREFIX
    # is still accepted for the same value.
    day1_cluster_name_strip_prefix: str = Field(
        default="ocp4-",
        validation_alias=AliasChoices("DAY1_CLUSTER_NAME_STRIP_PREFIX", "MCE_CLUSTER_NAME_PREFIX"),
    )

    # ── Cache (ADR-0011): seconds, never longer than a minute ────────────────
    day1_cache_ttl_seconds: float = Field(default=30.0, gt=0, le=60)

    # ── Day2 service (addon drift) ───────────────────────────────────────────
    day2_service_url: AnyHttpUrl = AnyHttpUrl("http://wingman-day2:8002")
    day2_timeout_seconds: float = Field(default=5.0, gt=0, le=60)

    # ── OpenShift OAuth (login) ──────────────────────────────────────────────
    openshift_oauth_host: str = ""
    openshift_api_host: str = ""
    openshift_oauth_client_id: str = ""
    openshift_oauth_client_secret: SecretStr = SecretStr("")
    openshift_oauth_redirect_uri: str = ""
    openshift_ssl_verify: str = "true"
    openshift_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    # ── Dev login (local and minikube only) ──────────────────────────────────
    dev_auth_enabled: bool = False
    dev_auth_secret: SecretStr = SecretStr("")

    # ── GitLab webhook (cache invalidation); empty secret = endpoint off ─────
    gitlab_webhook_secret: SecretStr = SecretStr("")

    # ── Live cluster status from the MCE hubs (off by default) ───────────────
    cluster_status_enabled: bool = False
    mce_api_domain: str = ""
    mce_tokens_file: Path = Path("/etc/wingman/mce-tokens/tokens")
    mce_ssl_verify: str = "true"
    mce_infraenv_namespace: str = ""
    mce_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    # ── Live status stream ───────────────────────────────────────────────────
    day1_status_poll_seconds: float = Field(default=30.0, ge=5, le=600)

    # ── Cluster nodes from server-scan, uninstall through the orchestrator ───
    # (ADR-0038; both off by default). Empty URLs switch them off: the routes
    # answer 501. DAY1_FAKE_FLEET replaces both with fakes, in development only.
    server_scan_url: str = ""
    server_scan_ui_url: str = ""
    server_scan_token: SecretStr = SecretStr("")
    server_scan_ssl_verify: str = "true"
    server_scan_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    workflows_api_url: str = ""
    workflows_ssl_verify: str = "true"
    workflows_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    day1_fake_fleet: bool = False

    @field_validator("specs_root_path")
    @classmethod
    def _specs_root_is_a_repo_path(cls, value: str) -> str:
        RepoPath(value)
        return value

    @field_validator("day1_cluster_name_strip_prefix")
    @classmethod
    def _prefix_is_a_name_prefix(cls, value: str) -> str:
        if value and (not value.endswith("-") or not value[:-1].replace("-", "").isalnum()):
            raise ValueError("DAY1_CLUSTER_NAME_STRIP_PREFIX must be empty or like 'ocp4-'")
        return value

    @field_validator("server_scan_url", "server_scan_ui_url", "workflows_api_url")
    @classmethod
    def _empty_or_an_http_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parts = urlsplit(value)
        if value and (parts.scheme not in ("http", "https") or not parts.netloc):
            raise ValueError(f"{value!r} must be empty or an http(s):// URL")
        return value

    @model_validator(mode="after")
    def _uninstall_has_server_scan(self) -> Self:
        """The uninstall reads the server from server-scan first; without it, it cannot run."""
        if self.workflows_api_url and not self.server_scan_url and not self.day1_fake_fleet:
            raise ValueError(
                "WORKFLOWS_API_URL needs SERVER_SCAN_URL: an uninstall checks the server "
                "in server-scan before it starts"
            )
        return self

    @model_validator(mode="after")
    def _login_is_possible_and_safe(self) -> Self:
        """Dev login needs a strong secret; without it, OpenShift OAuth must be complete."""
        if self.dev_auth_enabled:
            if len(self.dev_auth_secret.get_secret_value()) < MIN_DEV_AUTH_SECRET_LENGTH:
                raise ValueError(
                    "DEV_AUTH_ENABLED=true needs DEV_AUTH_SECRET of at least "
                    f"{MIN_DEV_AUTH_SECRET_LENGTH} characters: without it anyone can mint "
                    "an admin session"
                )
            return self
        missing = [
            name
            for name, value in (
                ("OPENSHIFT_API_HOST", self.openshift_api_host),
                ("OPENSHIFT_OAUTH_CLIENT_ID", self.openshift_oauth_client_id),
                (
                    "OPENSHIFT_OAUTH_CLIENT_SECRET",
                    self.openshift_oauth_client_secret.get_secret_value(),
                ),
                ("OPENSHIFT_OAUTH_REDIRECT_URI", self.openshift_oauth_redirect_uri),
            )
            if not value.strip()
        ]
        if missing:
            raise ValueError(
                "nobody could log in: set " + ", ".join(missing) + " (OpenShift OAuth), "
                "or DEV_AUTH_ENABLED=true with a DEV_AUTH_SECRET for local use"
            )
        return self

    @property
    def openshift_tls_verify(self) -> bool | str:
        """``OPENSHIFT_SSL_VERIFY`` parsed."""
        return tls_verify(self.openshift_ssl_verify)

    @property
    def mce_tls_verify(self) -> bool | str:
        """``MCE_SSL_VERIFY`` parsed."""
        return tls_verify(self.mce_ssl_verify)

    @property
    def server_scan_tls_verify(self) -> bool | str:
        """``SERVER_SCAN_SSL_VERIFY`` parsed."""
        return tls_verify(self.server_scan_ssl_verify)

    @property
    def workflows_tls_verify(self) -> bool | str:
        """``WORKFLOWS_SSL_VERIFY`` parsed."""
        return tls_verify(self.workflows_ssl_verify)

    @property
    def server_scan_ui_base(self) -> str:
        """Where node links point: ``SERVER_SCAN_UI_URL``, else ``SERVER_SCAN_URL``."""
        return self.server_scan_ui_url or self.server_scan_url


def check_runtime(settings: Day1Settings, runtime: RuntimeSettings) -> None:
    """Refuse to start with ``DAY1_FAKE_FLEET=true`` outside development (ADR-0009).

    The fake fleet invents servers and pretends to uninstall them; anywhere
    but a developer's machine that would show nodes that do not exist.
    """
    if settings.day1_fake_fleet and runtime.environment is not Environment.DEVELOPMENT:
        raise ValueError(
            "DAY1_FAKE_FLEET=true is refused unless WINGMAN_ENVIRONMENT=development "
            f"(it is {runtime.environment.value})"
        )
