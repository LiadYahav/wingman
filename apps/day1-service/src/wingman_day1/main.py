"""The composition root: the only module that builds adapters and wires the use cases.

    uvicorn wingman_day1.main:app --port 8001

``app`` is built on first access (PEP 562), so importing this module reads no
settings. ``create_app`` takes ready-made settings and adapters, which is how
the tests build the whole service on the in-memory GitLab and the fakes.

``WINGMAN_GIT_BACKEND=fake`` runs on an in-memory GitLab seeded from
``dev/gitlab-fixtures`` (local development and E2E); settings refuse it in
production (ADR-0009). ``DAY1_FAKE_FLEET=true`` does the same for the MCE
hubs, server-scan, the workflows orchestrator and segments-manager, from
``dev/fleet-fixtures``, in development only, and shows Quick Links' demo
links file (ADR-0038, ADR-0039, ADR-0052).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
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
from wingman_core.infrastructure.warm_up import start_warm_up
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
from wingman_core.web.app_factory import create_base_app, ready_once
from wingman_day1 import platform_adapters as platform
from wingman_day1.api.deps import Day1Context
from wingman_day1.api.errors import register_day1_error_handlers
from wingman_day1.api.v1 import approvals as approvals_api
from wingman_day1.api.v1 import audit as audit_api
from wingman_day1.api.v1 import auth as auth_api
from wingman_day1.api.v1 import clusters as clusters_api
from wingman_day1.api.v1 import inventory as inventory_api
from wingman_day1.api.v1 import machine_configs as machine_configs_api
from wingman_day1.api.v1 import placement as placement_api
from wingman_day1.api.v1 import quick_links as quick_links_api
from wingman_day1.api.v1 import segments as segments_api
from wingman_day1.api.v1 import sites as sites_api
from wingman_day1.api.v1 import specs as specs_api
from wingman_day1.api.v1 import upgrades as upgrades_api
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
from wingman_day1.application.placement import PlacementService
from wingman_day1.application.rollouts import ROLLOUT_USER, RolloutService
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.application.status import StatusService
from wingman_day1.application.sync import SyncService
from wingman_day1.compose_inventory import add_server_workflow, inventory_service
from wingman_day1.compose_quick_links import quick_links_service
from wingman_day1.compose_segments import segment_ledger, segments_service
from wingman_day1.domain.names import HostedClusterNaming
from wingman_day1.infrastructure.cached_day2 import CachedDay2Addons
from wingman_day1.infrastructure.cached_hub import CachedHubApi
from wingman_day1.infrastructure.cached_segments_manager import CachedSegmentLedger
from wingman_day1.infrastructure.cached_server_scan import CachedServerInventory
from wingman_day1.infrastructure.cached_workflows import CachedUninstallWorkflow
from wingman_day1.infrastructure.day2_client import HttpDay2Addons, HttpDay2Installs
from wingman_day1.infrastructure.hub_api import HttpHubApi, load_mce_access
from wingman_day1.infrastructure.merge_requests import (
    GitClusterProvisioner,
    GitRolloutMergeRequests,
    GitSpecChanges,
    MergeRequestWriter,
)
from wingman_day1.infrastructure.openshift_oauth import OpenShiftOAuth
from wingman_day1.infrastructure.repositories import CachedRepository
from wingman_day1.infrastructure.rollout_events import MetricRolloutEvents
from wingman_day1.platform_adapters import Close
from wingman_day1.ports import (
    AddServerWorkflow,
    ClusterDeleteWorkflow,
    Day2Addons,
    Day2Installs,
    HubApi,
    IdentityProvider,
    ProvisionWorkflow,
    SegmentLedger,
    ServerInventory,
    UninstallWorkflow,
    UpgradeWorkflow,
)
from wingman_day1.settings import Day1Settings, check_runtime

SERVICE = "day1"
SERVICE_USER: Final = User(username="system:wingman-day1", role=Role.VIEWER)
"""Who day1 is when it asks day2 for installed addons (a short-lived viewer session)."""
SERVICE_TOKEN_TTL: Final = timedelta(minutes=5)
RUNS_TTL_SECONDS: Final = 10.0
"""The longest an uninstall run's status is cached: the web polls a running one."""
HUB_TTL_SECONDS: Final = 10.0
"""The longest live status and the nodes view cache an MCE read (ADR-0041)."""
PLACEMENT_TTL_SECONDS: Final = 5.0
"""The longest placement keeps an MCE's nodes and pods: read when a create asks (ADR-0050)."""
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
    placement_api.router,
    quick_links_api.router,
    inventory_api.router,
    segments_api.router,
    upgrades_api.router,
    approvals_api.router,
    audit_api.router,
    webhooks_api.router,
)


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
    provision: ProvisionWorkflow | None = None
    """The provision-cluster workflow; ``None`` unless ``DAY1_PROVISIONER=workflow`` (ADR-0042)."""
    day2_installs: Day2Installs | None = None
    add_server: AddServerWorkflow | None = None
    """The add-server-to-mce workflow wherever the orchestrator is (ADR-0057)."""
    """Day2 opening a rollout's add-on MRs (ADR-0044); ``None``: listed for a person instead."""
    upgrade: UpgradeWorkflow | None = None
    """The upgrade-cluster workflow; ``None`` unless ``DAY1_UPGRADES`` (ADR-0055)."""
    closers: tuple[Close, ...] = field(default=())


def build_adapters(
    settings: Day1Settings,
    runtime: RuntimeSettings,
    *,
    metrics: WingmanMetrics,
    service_token: Callable[[], str],
    rollout_token: Callable[[], str] | None = None,
    clock: Clock = system_clock,
) -> Adapters:
    """The real adapters for these settings (or the in-memory GitLab, for ``fake``).

    ``service_token`` mints the short-lived session day1 presents to day2;
    ``rollout_token`` the admin one a flavor's rollout asks day2 to install
    add-ons with (ADR-0044).
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
    day2_installs: Day2Installs | None = None
    if rollout_token is not None:
        installs = HttpDay2Installs(
            base_url=str(settings.day2_service_url),
            token=rollout_token,
            metrics=metrics,
        )
        closers.append(installs.aclose)
        day2_installs = installs
    hub: HubApi | None = None
    if settings.cluster_status_enabled and not settings.day1_fake_fleet:
        access = load_mce_access(settings.mce_tokens_file)
        hub_api = HttpHubApi(
            tokens=access.tokens,
            urls=access.urls,
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
    fake_hub, inventory, uninstall = platform.fleet_adapters(
        settings, metrics=metrics, clock=clock, closers=closers
    )
    return Adapters(
        gitlab=InstrumentedGitLab(inner, metrics),
        day2=day2,
        hub=fake_hub or hub,
        identity=identity,
        inventory=inventory,
        uninstall=uninstall,
        ledger=segment_ledger(settings, metrics=metrics, closers=closers),
        provision=platform.provision_workflow(
            settings, metrics=metrics, clock=clock, closers=closers
        ),
        upgrade=platform.upgrade_workflow(settings, metrics=metrics, clock=clock, closers=closers),
        add_server=add_server_workflow(
            settings, inventory=inventory, metrics=metrics, clock=clock, closers=closers
        ),
        day2_installs=day2_installs,
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
    metrics: WingmanMetrics | None = None,
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
    day1_writer = MergeRequestWriter(gitlab, day1, repo=Repo.DAY1, label="day1", clock=clock)
    provisioner = GitClusterProvisioner(day1_writer)
    rollout_writer = GitRolloutMergeRequests(gitlab, day1, day1_writer)
    # server-scan's fleet rows, one cache for the nodes view, placement and Inventory
    inventory = (
        CachedServerInventory(adapters.inventory, cache, ttl=ttl)
        if adapters.inventory is not None
        else None
    )
    # Placement always runs (ADR-0050). An MCE's nodes, pods and Agents are read when a
    # create asks, kept for seconds; without live reads it decides on Git and server-scan.
    placement = PlacementService(
        day1,
        site_catalog,
        (
            CachedHubApi(adapters.hub, cache, ttl=PLACEMENT_TTL_SECONDS)
            if adapters.hub is not None
            else None
        ),
        inventory=inventory,
        min_free_pods=settings.placement_min_free_pods,
        specs=spec_catalog,
        infraenv_namespace=settings.mce_infraenv_namespace or None,
        record=metrics.observe_placement if metrics is not None else None,
    )
    cluster_service = ClusterService(
        day1,
        site_catalog,
        spec_catalog,
        provisioner,
        machine_configs,
        naming=naming,
        provision=adapters.provision,
        placement=placement,
        versions_by_workflow=settings.day1_upgrades,
    )
    drift = DriftService(
        cluster_service,
        spec_catalog,
        CachedDay2Addons(adapters.day2, cache, ttl=ttl),
        machine_configs,
        day1,
    )
    repos = {RepoKey.DAY1: day1, RepoKey.SPECS: specs_repo}
    # One cache of hub reads for live status and the nodes view, shared by every user (ADR-0041)
    hub = (
        CachedHubApi(adapters.hub, cache, ttl=min(ttl, HUB_TTL_SECONDS))
        if adapters.hub is not None
        else None
    )
    # InfraEnvs rarely change: their list is kept longer than live status's reads (ADR-0040)
    infra_env_hub = (
        CachedHubApi(adapters.hub, cache, ttl=settings.mce_infraenv_cache_seconds)
        if adapters.hub is not None
        else None
    )
    nodes: NodeService | None = None
    if hub is not None:
        runs_ttl = min(ttl, RUNS_TTL_SECONDS)
        nodes = NodeService(
            hub,
            cluster_service,
            inventory=inventory,
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
    sync = SyncService(
        cluster_service, spec_catalog, drift, machine_configs, provisioner, day1, rollout_writer
    )
    rollouts = RolloutService(
        cluster_service,
        spec_catalog,
        sync,
        drift,
        machine_configs,
        day1,
        rollout_writer,
        day2=adapters.day2_installs,
        events=MetricRolloutEvents(metrics),
        clock=clock,
    )
    fake_ui = FAKE_SEGMENTS_MANAGER_UI if settings.day1_fake_fleet else ""
    quick_links = quick_links_service(settings, site_catalog)
    dev_secret = settings.dev_auth_secret.get_secret_value() if settings.dev_auth_enabled else None
    return Day1Context(
        clusters=cluster_service,
        sites=site_catalog,
        specs=spec_catalog,
        approvals=ApprovalService(gitlab, repos, versions_by_workflow=settings.day1_upgrades),
        audit=AuditService(repos),
        drift=drift,
        imports=ImportService(cluster_service, spec_catalog, drift, machine_configs, provisioner),
        sync=sync,
        rollouts=rollouts,
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
                hub,
                cluster_service,
                naming=naming,
                infraenv_namespace=settings.mce_infraenv_namespace or None,
                infra_envs=infra_env_hub,
            )
            if hub is not None
            else None
        ),
        webhook_secret=settings.gitlab_webhook_secret.get_secret_value() or None,
        status_poll_seconds=settings.day1_status_poll_seconds,
        segments_manager_ui_url=settings.segments_manager_ui_base or fake_ui or None,
        placement=placement,
        quick_links=quick_links,
        segments=segments_service(adapters.ledger, cache, cluster_service, ttl=ttl),
        upgrades=platform.upgrade_service(settings, adapters.upgrade, cluster_service),
        inventory=inventory_service(
            settings,
            site_catalog,
            inventory=inventory,
            infra_envs=infra_env_hub,
            workflows=adapters.add_server,
            cache=cache,
        ),
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
        rollout_token=lambda: service_tokens.issue(ROLLOUT_USER),
        clock=clock,
    )
    context = build_context(
        settings=settings,
        auth=auth,
        adapters=adapters,
        session_tokens=session_tokens,
        cache=TtlCache(),
        clock=clock,
        metrics=metrics,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        warm = start_warm_up("day1", lambda: warm_up(context))
        yield
        warm.cancel()
        await context.rollouts.close()
        for close in adapters.closers:
            await close()

    gitlab = adapters.gitlab
    day1_project = project_ref(settings.day1_gitlab_project_id)
    specs_project = project_ref(settings.specs_gitlab_project_id)

    async def gitlab_ready() -> None:
        # Both projects: a wrong SPECS_GITLAB_PROJECT_ID (or a token without
        # access, which GitLab answers 404) must not look like an empty specs list.
        # Asked only until it passes once (ADR-0054): a later outage is the
        # requests' to report, so it does not take every pod out of the Service.
        await gitlab.get_project(day1_project)
        await gitlab.get_project(specs_project)

    app = create_base_app(
        title="Wingman day1",
        version=runtime.version,
        commit=runtime.commit,
        api_prefix="/api/day1",
        metrics=metrics,
        session_tokens=session_tokens,
        readiness={"gitlab": ready_once(gitlab_ready)},
        lifespan=lifespan,
    )
    app.state.day1 = context
    register_day1_error_handlers(app)
    for router in ROUTERS:
        app.include_router(router)
    return app


async def warm_up(context: Day1Context) -> None:
    """What a new replica's first page reads: the cluster list, every last change, the flavors."""
    await asyncio.gather(context.clusters.clusters(), context.specs.entries())


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """``wingman_day1.main:app``, built from the environment on first access."""
    global _app
    if name != "app":
        raise AttributeError(name)
    if _app is None:
        _app = create_app()
    return _app
