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

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from wingman_core.domain.git import RepoPath

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
    # Production strips "ocp4-" (openshift-prod-x-site1 in hcp-prod-x-site1);
    # the GitHub sandbox keeps the whole stem: set it to "" there. The legacy
    # MCE_CLUSTER_NAME_PREFIX (the chart's clusterStatus.clusterNamePrefix) is
    # accepted for the same value.
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

    # ── Build identity (wingman_build_info) ──────────────────────────────────
    wingman_version: str = "0.2.0"
    wingman_commit: str = "unknown"

    # ── WINGMAN_GIT_BACKEND=fake only: the repo trees to seed it with ────────
    wingman_fixtures_dir: Path | None = None
    """Defaults to ``dev/gitlab-fixtures`` of the checkout."""

    # ── Live status stream ───────────────────────────────────────────────────
    day1_status_poll_seconds: float = Field(default=30.0, ge=5, le=600)

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
    def webhook_enabled(self) -> bool:
        """The GitLab webhook endpoint exists only with a secret to check (fail closed)."""
        return bool(self.gitlab_webhook_secret.get_secret_value())
