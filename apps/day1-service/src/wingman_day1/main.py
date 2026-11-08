"""The composition root: the only module that builds adapters and wires the use cases.

    uvicorn wingman_day1.main:app --port 8001

``app`` is built on first access (PEP 562), so importing this module reads no
settings. ``create_app`` takes ready-made settings and adapters, which is how
the tests build the whole service on the in-memory GitLab and the fakes.

``WINGMAN_GIT_BACKEND=fake`` runs on an in-memory GitLab seeded from
``dev/gitlab-fixtures`` (local development and E2E); settings refuse it in
production (ADR-0009).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Final

from fastapi import FastAPI
from prometheus_client import CollectorRegistry

from wingman_core.domain.mr_conventions import Repo
from wingman_core.domain.users import Role, User
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.infrastructure.gitlab import GitLabHttpAdapter
from wingman_core.infrastructure.gitlab.http import build_client
from wingman_core.infrastructure.session_tokens import SessionTokens
from wingman_core.observability.instrumented_gitlab import InstrumentedGitLab
from wingman_core.observability.metrics import WingmanMetrics
from wingman_core.ports.clock import Clock, system_clock
from wingman_core.ports.gitlab import GitLabPort
from wingman_core.settings import AuthSettings, GitBackend, GitLabSettings, RuntimeSettings
from wingman_core.web.app_factory import create_base_app
from wingman_day1.api.deps import Day1Context
from wingman_day1.api.errors import register_day1_error_handlers
from wingman_day1.api.v1 import approvals as approvals_api
from wingman_day1.api.v1 import audit as audit_api
from wingman_day1.api.v1 import auth as auth_api
from wingman_day1.api.v1 import clusters as clusters_api
from wingman_day1.api.v1 import machine_configs as machine_configs_api
from wingman_day1.api.v1 import sites as sites_api
from wingman_day1.api.v1 import specs as specs_api
from wingman_day1.api.v1 import webhooks as webhooks_api
from wingman_day1.application.approvals import ApprovalService, RepoKey
from wingman_day1.application.audit import AuditService
from wingman_day1.application.auth import AuthService
from wingman_day1.application.clusters import ClusterService
from wingman_day1.application.drift import DriftService
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.application.status import StatusService
from wingman_day1.domain.names import HostedClusterNaming
from wingman_day1.infrastructure.cached_day2 import CachedDay2Addons
from wingman_day1.infrastructure.day2_client import HttpDay2Addons
from wingman_day1.infrastructure.hub_api import HttpHubApi, load_mce_tokens
from wingman_day1.infrastructure.merge_requests import (
    GitClusterProvisioner,
    GitSpecChanges,
    MergeRequestWriter,
)
from wingman_day1.infrastructure.openshift_oauth import OpenShiftOAuth
from wingman_day1.infrastructure.repositories import CachedRepository
from wingman_day1.ports import Day2Addons, HubApi, IdentityProvider
from wingman_day1.settings import Day1Settings

SERVICE = "day1"
SERVICE_USER: Final = User(username="system:wingman-day1", role=Role.VIEWER)
"""Who day1 is when it asks day2 for installed addons (a short-lived viewer session)."""
SERVICE_TOKEN_TTL: Final = timedelta(minutes=5)
ROUTERS: Final = (
    auth_api.router,
    clusters_api.router,
    sites_api.sites_router,
    sites_api.mces_router,
    specs_api.router,
    machine_configs_api.router,
    approvals_api.router,
    audit_api.router,
    webhooks_api.router,
)

Close = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Adapters:
    """The outside world, as ports. Tests pass fakes; ``build_adapters`` the real ones."""

    gitlab: GitLabPort
    day2: Day2Addons
    hub: HubApi | None = None
    """``None`` when ``CLUSTER_STATUS_ENABLED`` is off."""
    identity: IdentityProvider | None = None
    """``None`` when OpenShift OAuth is not configured (dev login only)."""
    closers: tuple[Close, ...] = field(default=())


def project_ref(value: str) -> int | str:
    """A project setting: a numeric id, or a ``group/project`` path."""
    return int(value) if value.isdigit() else value.strip("/")


def build_adapters(
    settings: Day1Settings,
    runtime: RuntimeSettings,
    *,
    metrics: WingmanMetrics,
    service_token: Callable[[], str],
    clock: Clock = system_clock,
) -> Adapters:
    """The real adapters for these settings (or the in-memory GitLab, for ``fake``).

    ``service_token`` mints the short-lived session day1 presents to day2.
    """
    closers: list[Close] = []
    if runtime.git_backend is GitBackend.FAKE:
        from wingman_core.testing.fixtures import (
            default_fixture_root,
            load_fixture_projects,
            seed_fake,
        )

        fake = InMemoryGitLab(clock=clock)
        root = settings.wingman_fixtures_dir or default_fixture_root()
        seed_fake(fake, load_fixture_projects(root))
        inner: GitLabPort = fake
    else:
        adapter = GitLabHttpAdapter(build_client(GitLabSettings()))
        closers.append(adapter.aclose)
        inner = adapter
    day2 = HttpDay2Addons(
        base_url=str(settings.day2_service_url),
        token=service_token,
        timeout_seconds=settings.day2_timeout_seconds,
        metrics=metrics,
    )
    closers.append(day2.aclose)
    hub: HubApi | None = None
    if settings.cluster_status_enabled:
        hub_api = HttpHubApi(
            tokens=load_mce_tokens(settings.mce_tokens_file),
            domain=settings.mce_api_domain,
            verify=settings.mce_tls_verify,
            timeout_seconds=settings.mce_timeout_seconds,
            metrics=metrics,
        )
        closers.append(hub_api.aclose)
        hub = hub_api
    identity: IdentityProvider | None = None
    if settings.openshift_api_host and settings.openshift_oauth_client_id:
        oauth = OpenShiftOAuth(
            oauth_host=settings.openshift_oauth_host,
            api_host=settings.openshift_api_host,
            client_id=settings.openshift_oauth_client_id,
            client_secret=settings.openshift_oauth_client_secret,
            redirect_uri=settings.openshift_oauth_redirect_uri,
            verify=settings.openshift_tls_verify,
            timeout_seconds=settings.openshift_timeout_seconds,
            metrics=metrics,
        )
        closers.append(oauth.aclose)
        identity = oauth
    return Adapters(
        gitlab=InstrumentedGitLab(inner, metrics),
        day2=day2,
        hub=hub,
        identity=identity,
        closers=tuple(closers),
    )


def build_context(
    *,
    settings: Day1Settings,
    auth: AuthSettings,
    adapters: Adapters,
    session_tokens: SessionTokens,
    cache: TtlCache,
    clock: Clock = system_clock,
) -> Day1Context:
    """Wire the use cases onto the adapters."""
    ttl = settings.day1_cache_ttl_seconds
    gitlab = adapters.gitlab
    day1 = CachedRepository(
        gitlab,
        cache,
        key=RepoKey.DAY1,
        project=project_ref(settings.day1_gitlab_project_id),
        ttl=ttl,
    )
    specs_repo = CachedRepository(
        gitlab,
        cache,
        key=RepoKey.SPECS,
        project=project_ref(settings.specs_gitlab_project_id),
        ttl=ttl,
    )
    naming = HostedClusterNaming(settings.day1_cluster_name_strip_prefix)
    site_catalog = SiteCatalog(day1)
    machine_configs = MachineConfigService(day1, specs_repo)
    spec_catalog = SpecCatalog(
        specs_repo,
        GitSpecChanges(
            MergeRequestWriter(gitlab, specs_repo, repo=Repo.SPECS, label="specs", clock=clock),
            specs_root=settings.specs_root_path,
        ),
        specs_root=settings.specs_root_path,
    )
    cluster_service = ClusterService(
        day1,
        site_catalog,
        spec_catalog,
        GitClusterProvisioner(
            MergeRequestWriter(gitlab, day1, repo=Repo.DAY1, label="day1", clock=clock)
        ),
        naming=naming,
    )
    repos = {RepoKey.DAY1: day1, RepoKey.SPECS: specs_repo}
    dev_secret = settings.dev_auth_secret.get_secret_value() if settings.dev_auth_enabled else None
    return Day1Context(
        clusters=cluster_service,
        sites=site_catalog,
        specs=spec_catalog,
        approvals=ApprovalService(gitlab, repos),
        audit=AuditService(repos),
        drift=DriftService(
            cluster_service, spec_catalog, CachedDay2Addons(adapters.day2, cache, ttl=ttl)
        ),
        auth=AuthService(
            session_tokens,
            identity=adapters.identity,
            admin_groups=auth.admin_groups,
            viewer_groups=auth.viewer_groups,
            dev_secret=dev_secret,
        ),
        repos=repos,
        machine_configs=machine_configs,
        status=(
            StatusService(
                adapters.hub,
                cluster_service,
                naming=naming,
                infraenv_namespace=settings.mce_infraenv_namespace or None,
            )
            if adapters.hub is not None
            else None
        ),
        webhook_secret=settings.gitlab_webhook_secret.get_secret_value() or None,
        status_poll_seconds=settings.day1_status_poll_seconds,
    )


def create_app(
    *,
    settings: Day1Settings | None = None,
    auth: AuthSettings | None = None,
    runtime: RuntimeSettings | None = None,
    adapters: Adapters | None = None,
    clock: Clock = system_clock,
) -> FastAPI:
    """The day1 FastAPI app. Settings default to the environment; adapters to the real ones."""
    settings = settings or Day1Settings()
    auth = auth or AuthSettings()
    runtime = runtime or RuntimeSettings()
    metrics = WingmanMetrics(
        CollectorRegistry(),
        component=SERVICE,
        version=settings.wingman_version,
        commit=settings.wingman_commit,
    )
    secret = auth.jwt_secret_key.get_secret_value()
    session_tokens = SessionTokens(secret, ttl=timedelta(hours=auth.jwt_expiry_hours), clock=clock)
    service_tokens = SessionTokens(secret, ttl=SERVICE_TOKEN_TTL, clock=clock)
    adapters = adapters or build_adapters(
        settings,
        runtime,
        metrics=metrics,
        service_token=lambda: service_tokens.issue(SERVICE_USER),
        clock=clock,
    )
    context = build_context(
        settings=settings,
        auth=auth,
        adapters=adapters,
        session_tokens=session_tokens,
        cache=TtlCache(),
        clock=clock,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        for close in adapters.closers:
            await close()

    gitlab = adapters.gitlab
    day1_project = project_ref(settings.day1_gitlab_project_id)
    app = create_base_app(
        title="Wingman day1",
        version=settings.wingman_version,
        metrics=metrics,
        session_tokens=session_tokens,
        readiness={"gitlab": lambda: gitlab.get_project(day1_project)},
        lifespan=lifespan,
    )
    app.state.day1 = context
    register_day1_error_handlers(app)
    for router in ROUTERS:
        app.include_router(router)
    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """``wingman_day1.main:app``, built from the environment on first access."""
    global _app
    if name != "app":
        raise AttributeError(name)
    if _app is None:
        _app = create_app()
    return _app
