"""Day1's settings: the only place day1 reads its environment.

The GitLab connection, session tokens and runtime come from
``wingman_core.settings``; this adds what only day1 needs. Environment
variable names are the legacy service's where the meaning is unchanged, so
the chart's ConfigMap keeps working. Settings fail closed (ADR-0009): a
configuration that would let anyone in, or let nobody in, refuses to start.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final, Literal, Self
from urllib.parse import urlsplit

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from wingman_core.domain.git import RepoPath
from wingman_core.settings import Environment, RuntimeSettings
from wingman_day1.domain.quick_links import (
    DEFAULT_ARGOCD_TEMPLATE,
    DEFAULT_CONSOLE_TEMPLATE,
    template_problems,
)

MIN_DEV_AUTH_SECRET_LENGTH: Final = 32
_DNS_LABEL: Final = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_DOMAIN: Final = re.compile(
    r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)*$"
)


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
    mce_infraenv_cache_seconds: float = Field(default=600.0, ge=0, le=86400)
    """How long a hub's InfraEnv list is kept (ADR-0040); they rarely change. 0: not kept."""
    mce_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    # ── Live status stream ───────────────────────────────────────────────────
    day1_status_poll_seconds: float = Field(default=30.0, ge=5, le=600)

    # ── Cluster nodes from server-scan, uninstall through the orchestrator ───
    # (ADR-0038; both off by default). Empty URLs switch them off: the routes
    # answer 501. DAY1_FAKE_FLEET replaces both with fakes, in development only.
    server_scan_url: str = ""
    server_scan_ui_url: str = ""
    server_scan_token: SecretStr = SecretStr("")
    # server-scan's admin token, for the Server Scan area's maintenance toggle
    # (ADR-0048's 3.23.0 amendment) and its Jobs page, reads too (3.32.0) only.
    # Empty with a viewer token: both are off; empty with none: server-scan runs
    # with auth off and takes them as is.
    server_scan_admin_token: SecretStr = SecretStr("")
    # server-scan's auditor token, for a server's History only (ADR-0048's 3.25.0
    # amendment). Empty with a viewer token: History is off; empty with none:
    # server-scan runs with auth off and serves it as is.
    server_scan_auditor_token: SecretStr = SecretStr("")
    server_scan_ssl_verify: str = "true"
    server_scan_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    workflows_api_url: str = ""
    workflows_ssl_verify: str = "true"
    workflows_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    day1_fake_fleet: bool = False

    # ── How a create is proposed (ADR-0042) ──────────────────────────────────
    # merge-request (default): Wingman's own commit and merge request. workflow:
    # start the platform's provision-cluster workflow, which opens the merge
    # request itself; needs WORKFLOWS_API_URL (or DAY1_FAKE_FLEET in development).
    day1_provisioner: Literal["merge-request", "workflow"] = "merge-request"

    # ── Upgrades through the upgrade-cluster workflow (ADR-0055) ─────────────
    # Off by default. On: the cluster page starts the platform's upgrade-cluster
    # workflow, shows its run and sends its decisions, and while it is on an edit
    # may not change mastertag or a workertag, nor add pausedUntil. Needs
    # WORKFLOWS_API_URL (or DAY1_FAKE_FLEET in development). The targets read
    # waits for a short run the orchestrator waits up to 60 s for: its own timeout.
    day1_upgrades: bool = False
    workflows_targets_timeout_seconds: float = Field(default=65.0, gt=0, le=120)

    # ── Inventory Management: adding servers (ADR-0057; off by default) ──────
    # true: admins add servers to an MCE's InfraEnv pool by starting the
    # platform's add-server-to-mce workflow; needs WORKFLOWS_API_URL (or
    # DAY1_FAKE_FLEET in development). The page itself needs SERVER_SCAN_URL.
    day1_add_servers: bool = False

    # ── MCE placement (ADR-0050): always on; this needs the hubs ─────────────
    # The cost of one hosted control plane: with CLUSTER_STATUS_ENABLED, an MCE
    # is offered for a new cluster only with at least this many free pods
    # (allocatable less in use) on its workers (masters, infra nodes, tainted,
    # cordoned or NotReady nodes left out). Without it, not checked.
    placement_min_free_pods: int = Field(default=70, ge=0, le=100_000)

    # ── segments-manager: a cluster's EPG, checked against Git (ADR-0039) ────
    # Off by default. SEGMENTS_MANAGER_URL is its API (reads need no token);
    # day1 only reads one segment, never writes. SEGMENTS_MANAGER_UI_URL is
    # where the cluster page's links point (default: the API's URL). Empty
    # both: no EPG and no link. DAY1_FAKE_FLEET replaces it with a fake.
    segments_manager_url: str = ""
    segments_manager_ui_url: str = ""
    segments_manager_ssl_verify: str = "true"
    segments_manager_timeout_seconds: float = Field(default=5.0, gt=0, le=60)

    # ── Quick Links: the launcher page (ADR-0052; admins only) ───────────────
    # A card per cluster opens its ArgoCD, with its console beside it: the hub
    # Wingman runs on (QUICK_LINKS_HUB_NAME; empty: none) and every MCE of the
    # day1 repo, at the URL templates in their domain (QUICK_LINKS_DOMAIN, else
    # MCE_API_DOMAIN; the hub's: QUICK_LINKS_HUB_DOMAIN, else that). The team's
    # links, and the addresses of a cluster that does not follow the templates,
    # are the links file (a ConfigMap; re-read on every page load). Wingman
    # only lists the links: it never calls them.
    quick_links_file: Path = Path("/etc/wingman/quick-links/links.yaml")
    quick_links_hub_name: str = ""
    quick_links_hub_domain: str = ""
    quick_links_domain: str = ""
    quick_links_argocd_url_template: str = DEFAULT_ARGOCD_TEMPLATE
    quick_links_console_url_template: str = DEFAULT_CONSOLE_TEMPLATE

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

    @field_validator(
        "server_scan_url",
        "server_scan_ui_url",
        "workflows_api_url",
        "segments_manager_url",
        "segments_manager_ui_url",
    )
    @classmethod
    def _empty_or_an_http_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parts = urlsplit(value)
        if value and (parts.scheme not in ("http", "https") or not parts.netloc):
            raise ValueError(f"{value!r} must be empty or an http(s):// URL")
        return value

    @field_validator("quick_links_hub_name")
    @classmethod
    def _hub_is_a_cluster_name(cls, value: str) -> str:
        value = value.strip()
        if value and not _DNS_LABEL.match(value):
            raise ValueError("QUICK_LINKS_HUB_NAME must be empty or a cluster name (a DNS label)")
        return value

    @field_validator("quick_links_hub_domain", "quick_links_domain")
    @classmethod
    def _empty_or_a_domain(cls, value: str) -> str:
        value = value.strip().strip(".")
        if value and not _DOMAIN.match(value):
            raise ValueError(f"{value!r} must be empty or a domain such as example.internal")
        return value

    @field_validator("quick_links_argocd_url_template", "quick_links_console_url_template")
    @classmethod
    def _a_url_template(cls, value: str) -> str:
        value = value.strip()
        if problems := template_problems(value):
            raise ValueError("; ".join(problems))
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
    def _workflow_creates_have_an_orchestrator(self) -> Self:
        """Starting provision-cluster needs the orchestrator; without it no create could run."""
        if (
            self.day1_provisioner == "workflow"
            and not self.workflows_api_url
            and not self.day1_fake_fleet
        ):
            raise ValueError(
                "DAY1_PROVISIONER=workflow needs WORKFLOWS_API_URL: creates start the "
                "provision-cluster workflow there"
            )
        return self

    @model_validator(mode="after")
    def _upgrades_have_an_orchestrator(self) -> Self:
        """The upgrade is the orchestrator's workflow; without it no upgrade could start."""
        if self.day1_upgrades and not self.workflows_api_url and not self.day1_fake_fleet:
            raise ValueError(
                "DAY1_UPGRADES=true needs WORKFLOWS_API_URL: upgrades start the "
                "upgrade-cluster workflow there"
            )
        return self

    @model_validator(mode="after")
    def _adding_servers_has_an_orchestrator(self) -> Self:
        """Adding servers starts add-server-to-mce; without the orchestrator none could start."""
        if self.day1_add_servers and not self.workflows_api_url and not self.day1_fake_fleet:
            raise ValueError(
                "DAY1_ADD_SERVERS=true needs WORKFLOWS_API_URL: adding servers starts the "
                "add-server-to-mce workflow there"
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
    def segments_manager_tls_verify(self) -> bool | str:
        """``SEGMENTS_MANAGER_SSL_VERIFY`` parsed."""
        return tls_verify(self.segments_manager_ssl_verify)

    @property
    def server_scan_ui_base(self) -> str:
        """Where node links point: ``SERVER_SCAN_UI_URL``, else ``SERVER_SCAN_URL``."""
        return self.server_scan_ui_url or self.server_scan_url

    @property
    def segments_manager_ui_base(self) -> str:
        """Where the cluster page's links point: ``SEGMENTS_MANAGER_UI_URL``, else the API's URL."""
        return self.segments_manager_ui_url or self.segments_manager_url

    @property
    def quick_links_mce_domain(self) -> str:
        """The MCEs' domain on Quick Links: ``QUICK_LINKS_DOMAIN``, else ``MCE_API_DOMAIN``."""
        return self.quick_links_domain or self.mce_api_domain.strip().strip(".")

    @property
    def quick_links_hub_base_domain(self) -> str:
        """The hub's domain on Quick Links: ``QUICK_LINKS_HUB_DOMAIN``, else the MCEs'."""
        return self.quick_links_hub_domain or self.quick_links_mce_domain


def check_runtime(settings: Day1Settings, runtime: RuntimeSettings) -> None:
    """Refuse to start with ``DAY1_FAKE_FLEET=true`` outside development (ADR-0009).

    The fake fleet invents servers, segments and EPGs, and pretends to
    uninstall servers; anywhere but a developer's machine that would show
    nodes and networks that do not exist.
    """
    if settings.day1_fake_fleet and runtime.environment is not Environment.DEVELOPMENT:
        raise ValueError(
            "DAY1_FAKE_FLEET=true is refused unless WINGMAN_ENVIRONMENT=development "
            f"(it is {runtime.environment.value})"
        )
