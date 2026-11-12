"""The composition root: the only module that builds adapters and wires the use cases.

    uvicorn wingman_day1.main:app --port 8001

``app`` is built on first access (PEP 562), so importing this module reads no
settings. ``create_app`` takes ready-made settings and adapters, which is how
the tests build the whole service on the in-memory GitLab and the fakes.

``WINGMAN_GIT_BACKEND=fake`` runs on an in-memory GitLab seeded from
``dev/gitlab-fixtures`` (local development and E2E); settings refuse it in
production (ADR-0009). ``DAY1_FAKE_FLEET=true`` does the same for the MCE
hubs, server-scan, the workflows orchestrator and segments-manager, from
``dev/fleet-fixtures``, in development only (ADR-0038, ADR-0039).
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
from wingman_core.infrastructure.snapshots import RepoSnapshots
from wingman_core.observability.instrumented_gitlab import InstrumentedGitLab
from wingman_core.observability.metrics import WingmanMetrics
from wingman_core.ports.clock import Clock, system_clock
from wingman_core.ports.gitlab import GitLabPort
from wingman_core.settings import (
    AuthSettings,
    GitBackend,
    GitLabSettings,
    RuntimeSettings,
    project_ref,
)
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
from wingman_day1.application.imports import ImportService
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.application.network import NetworkService
from wingman_day1.application.nodes import NodeService
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.application.status import StatusService
from wingman_day1.application.sync import SyncService
from wingman_day1.domain.names import HostedClusterNaming
from wingman_day1.infrastructure.cached_day2 import CachedDay2Addons
from wingman_day1.infrastructure.cached_hub import CachedHubApi
from wingman_day1.infrastructure.cached_segments_manager import CachedSegmentLedger
from wingman_day1.infrastructure.cached_server_scan import CachedServerInventory
from wingman_day1.infrastructure.cached_workflows import CachedUninstallWorkflow
from wingman_day1.infrastructure.day2_client import HttpDay2Addons
from wingman_day1.infrastructure.hub_api import HttpHubApi, load_mce_tokens
from wingman_day1.infrastructure.merge_requests import (
    GitClusterProvisioner,
    GitSpecChanges,
    MergeRequestWriter,
)
from wingman_day1.infrastructure.openshift_oauth import OpenShiftOAuth
from wingman_day1.infrastructure.repositories import CachedRepository
from wingman_day1.infrastructure.segments_manager import HttpSegmentLedger
from wingman_day1.infrastructure.server_scan import HttpServerInventory
from wingman_day1.infrastructure.workflows_api import HttpUninstallWorkflow
from wingman_day1.ports import (
    ClusterDeleteWorkflow,
    Day2Addons,
    HubApi,
    IdentityProvider,
    SegmentLedger,
    ServerInventory,
    UninstallWorkflow,
)
from wingman_day1.settings import Day1Settings, check_runtime

SERVICE = "day1"
SERVICE_USER: Final = User(username="system:wingman-day1", role=Role.VIEWER)
"""Who day1 is when it asks day2 for installed addons (a short-lived viewer session)."""
SERVICE_TOKEN_TTL: Final = timedelta(minutes=5)
RUNS_TTL_SECONDS: Final = 10.0
"""The longest an uninstall run's status is cached: the web polls a running one."""
HUB_TTL_SECONDS: Final = 10.0
"""The longest the nodes view caches an MCE read (live status reads the hub directly)."""
FAKE_SERVER_SCAN_UI: Final = "http://server-scan.example"
"""Where the fake fleet's node links point when ``SERVER_SCAN_UI_URL`` is empty."""
FAKE_SEGMENTS_MANAGER_UI: Final = "http://segments-manager.example"
"""Where the fake fleet's segments-manager links point when no segments-manager URL is set."""
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
    """``None`` when ``CLUSTER_STATUS_ENABLED`` is off (the fake MCE with ``DAY1_FAKE_FLEET``)."""
    identity: IdentityProvider | None = None
    """``None`` when OpenShift OAuth is not configured (dev login only)."""
    delete_workflow: ClusterDeleteWorkflow | None = None
    """``None`` until the delete-cluster workflow exists (ADR-0033)."""
    inventory: ServerInventory | None = None
    """server-scan; ``None`` when ``SERVER_SCAN_URL`` is empty (ADR-0038)."""
    uninstall: UninstallWorkflow | None = None
    """The orchestrator's uninstall workflow; ``None`` when ``WORKFLOWS_API_URL`` is empty."""
    ledger: SegmentLedger | None = None
    """segments-manager; ``None`` when ``SEGMENTS_MANAGER_URL`` is empty (ADR-0039)."""
    closers: tuple[Close, ...] = field(default=())


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
        root = runtime.fixtures_dir or default_fixture_root()
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
    if settings.cluster_status_enabled and not settings.day1_fake_fleet:
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
    fake_hub, inventory, uninstall = _fleet_adapters(
        settings, metrics=metrics, clock=clock, closers=closers
    )
    return Adapters(
        gitlab=InstrumentedGitLab(inner, metrics),
        day2=day2,
        hub=fake_hub or hub,
        identity=identity,
        inventory=inventory,
        uninstall=uninstall,
        ledger=_segment_ledger(settings, metrics=metrics, closers=closers),
        closers=tuple(closers),
    )


def _segment_ledger(
    settings: Day1Settings, *, metrics: WingmanMetrics, closers: list[Close]
) -> SegmentLedger | None:
    """segments-manager, real or none; or, with the fake fleet, its fake (ADR-0039)."""
    if settings.day1_fake_fleet:
        from wingman_day1.infrastructure.fake_segments import (
            FakeSegmentLedger,
            default_segments_file,
            load_segments,
        )

        return FakeSegmentLedger(load_segments(default_segments_file()))
    if not settings.segments_manager_url:
        return None
    ledger = HttpSegmentLedger(
        base_url=settings.segments_manager_url,
        verify=settings.segments_manager_tls_verify,
        timeout_seconds=settings.segments_manager_timeout_seconds,
        metrics=metrics,
    )
    closers.append(ledger.aclose)
    return ledger


def _fleet_adapters(
    settings: Day1Settings, *, metrics: WingmanMetrics, clock: Clock, closers: list[Close]
) -> tuple[HubApi | None, ServerInventory | None, UninstallWorkflow | None]:
    """server-scan and the orchestrator, real or none; or the fake fleet (ADR-0038).

    The fake fleet is both fakes and a fake MCE, which then also serves live
    status and InfraEnvs.
    """
    if settings.day1_fake_fleet:
        from wingman_day1.infrastructure.fake_fleet import (
            FakeServerInventory,
            FakeUninstallWorkflow,
            default_fleet_file,
            load_fleet,
        )
        from wingman_day1.infrastructure.fake_mce import default_mce_file, load_fake_mce

        rows, runs = load_fleet(default_fleet_file())
        fake = FakeServerInventory(rows)
        workflow = FakeUninstallWorkflow(fake, clock=clock, runs=runs)
        naming = HostedClusterNaming(settings.day1_cluster_name_strip_prefix)
        mce = load_fake_mce(default_mce_file(), servers=rows, naming=naming)
        workflow.after_uninstall(mce.remove_server)
        return mce, fake, workflow
    inventory: ServerInventory | None = None
    if settings.server_scan_url:
        scan = HttpServerInventory(
            base_url=settings.server_scan_url,
            token=settings.server_scan_token.get_secret_value(),
            verify=settings.server_scan_tls_verify,
            timeout_seconds=settings.server_scan_timeout_seconds,
            metrics=metrics,
        )
        closers.append(scan.aclose)
        inventory = scan
    uninstall: UninstallWorkflow | None = None
    if settings.workflows_api_url:
        orchestrator = HttpUninstallWorkflow(
            base_url=settings.workflows_api_url,
            verify=settings.workflows_tls_verify,
            timeout_seconds=settings.workflows_timeout_seconds,
            metrics=metrics,
        )
        closers.append(orchestrator.aclose)
        uninstall = orchestrator
    return None, inventory, uninstall


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
    snapshots = RepoSnapshots(gitlab, cache, ttl=ttl)
    day1 = CachedRepository(
        gitlab,
        cache,
        key=RepoKey.DAY1,
        project=project_ref(settings.day1_gitlab_project_id),
        ttl=ttl,
        snapshots=snapshots,
    )
    specs_repo = CachedRepository(
        gitlab,
        cache,
        key=RepoKey.SPECS,
        project=project_ref(settings.specs_gitlab_project_id),
        ttl=ttl,
        snapshots=snapshots,
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
        machine_configs,
        specs_root=settings.specs_root_path,
    )
    provisioner = GitClusterProvisioner(
        MergeRequestWriter(gitlab, day1, repo=Repo.DAY1, label="day1", clock=clock)
    )
    cluster_service = ClusterService(
        day1, site_catalog, spec_catalog, provisioner, machine_configs, naming=naming
    )
    drift = DriftService(
        cluster_service,
        spec_catalog,
        CachedDay2Addons(adapters.day2, cache, ttl=ttl),
        machine_configs,
    )
    repos = {RepoKey.DAY1: day1, RepoKey.SPECS: specs_repo}
    nodes: NodeService | None = None
    if adapters.hub is not None:
        runs_ttl = min(ttl, RUNS_TTL_SECONDS)
        nodes = NodeService(
            CachedHubApi(adapters.hub, cache, ttl=min(ttl, HUB_TTL_SECONDS)),
            cluster_service,
            inventory=(
                CachedServerInventory(adapters.inventory, cache, ttl=ttl)
                if adapters.inventory is not None
                else None
            ),
            ui_url=settings.server_scan_ui_base or FAKE_SERVER_SCAN_UI,
            workflows=(
                CachedUninstallWorkflow(adapters.uninstall, cache, ttl=runs_ttl)
                if adapters.uninstall is not None
                else None
            ),
            infraenv_namespace=settings.mce_infraenv_namespace or None,
        )
    network = NetworkService(
        cluster_service,
        CachedSegmentLedger(adapters.ledger, cache, ttl=ttl)
        if adapters.ledger is not None
        else None,
    )
    fake_ui = FAKE_SEGMENTS_MANAGER_UI if settings.day1_fake_fleet else ""
    dev_secret = settings.dev_auth_secret.get_secret_value() if settings.dev_auth_enabled else None
    return Day1Context(
        clusters=cluster_service,
        sites=site_catalog,
        specs=spec_catalog,
        approvals=ApprovalService(gitlab, repos),
        audit=AuditService(repos),
        drift=drift,
        imports=ImportService(cluster_service, spec_catalog, drift, machine_configs, provisioner),
        sync=SyncService(cluster_service, spec_catalog, drift, machine_configs, provisioner),
        auth=AuthService(
            session_tokens,
            identity=adapters.identity,
            admin_groups=auth.admin_groups,
            viewer_groups=auth.viewer_groups,
            dev_secret=dev_secret,
        ),
        repos=repos,
        machine_configs=machine_configs,
        network=network,
        delete_workflow=adapters.delete_workflow,
        nodes=nodes,
        status=(
            StatusService(
                adapters.hub,
                cluster_service,
                naming=naming,
                infraenv_namespace=settings.mce_infraenv_namespace or None,
                infra_envs=CachedHubApi(
                    adapters.hub, cache, ttl=settings.mce_infraenv_cache_seconds
                ),
            )
            if adapters.hub is not None
            else None
        ),
        webhook_secret=settings.gitlab_webhook_secret.get_secret_value() or None,
        status_poll_seconds=settings.day1_status_poll_seconds,
        segments_manager_ui_url=settings.segments_manager_ui_base or fake_ui or None,
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
    check_runtime(settings, runtime)
    metrics = WingmanMetrics(
        CollectorRegistry(),
        component=SERVICE,
        version=runtime.version,
        commit=runtime.commit,
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
    specs_project = project_ref(settings.specs_gitlab_project_id)

    async def gitlab_ready() -> None:
        # Both projects: a wrong SPECS_GITLAB_PROJECT_ID (or a token without
        # access, which GitLab answers 404) must not look like an empty specs list.
        await gitlab.get_project(day1_project)
        await gitlab.get_project(specs_project)

    app = create_base_app(
        title="Wingman day1",
        version=runtime.version,
        commit=runtime.commit,
        api_prefix="/api/day1",
        metrics=metrics,
        session_tokens=session_tokens,
        readiness={"gitlab": gitlab_ready},
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
