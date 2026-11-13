"""The platform services' adapters: part of the composition root (``main.py``).

The workflows orchestrator (provision, uninstall and upgrade, ADR-0038,
ADR-0042, ADR-0055) and server-scan, real or none; or, with ``DAY1_FAKE_FLEET``
(development only), their fakes from ``dev/fleet-fixtures``. segments-manager's
is ``compose_segments``.
``main.build_adapters`` calls these; nothing else does.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_core.ports.clock import Clock
from wingman_day1.application.clusters import ClusterService
from wingman_day1.application.upgrades import UpgradeService
from wingman_day1.domain.names import HostedClusterNaming
from wingman_day1.infrastructure.cached_workflows import CachedUpgradeWorkflow
from wingman_day1.infrastructure.provision_workflow import HttpProvisionWorkflow
from wingman_day1.infrastructure.server_scan import HttpServerInventory
from wingman_day1.infrastructure.upgrade_workflow import HttpUpgradeWorkflow
from wingman_day1.infrastructure.workflows_api import HttpUninstallWorkflow
from wingman_day1.ports import (
    HubApi,
    ProvisionWorkflow,
    ServerInventory,
    UninstallWorkflow,
    UpgradeWorkflow,
)
from wingman_day1.settings import Day1Settings

Close = Callable[[], Awaitable[None]]
FLEET_RUNS_TTL_SECONDS: Final = 10.0
"""The longest the fleet's upgrade runs are kept: the clusters list reads them every 15 s."""


def provision_workflow(
    settings: Day1Settings, *, metrics: WingmanMetrics, clock: Clock, closers: list[Close]
) -> ProvisionWorkflow | None:
    """The provision-cluster workflow when creates start it; or, with the fake fleet, its fake."""
    if settings.day1_provisioner != "workflow":
        return None
    if settings.day1_fake_fleet:
        from wingman_day1.infrastructure.fake_provision import FakeProvisionWorkflow

        return FakeProvisionWorkflow(clock=clock)
    workflow = HttpProvisionWorkflow(
        base_url=settings.workflows_api_url,
        verify=settings.workflows_tls_verify,
        timeout_seconds=settings.workflows_timeout_seconds,
        metrics=metrics,
    )
    closers.append(workflow.aclose)
    return workflow


def fleet_adapters(
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


def upgrade_workflow(
    settings: Day1Settings, *, metrics: WingmanMetrics, clock: Clock, closers: list[Close]
) -> UpgradeWorkflow | None:
    """The upgrade-cluster workflow when upgrades are on; or, with the fake fleet, its fake."""
    if not settings.day1_upgrades:
        return None
    if settings.day1_fake_fleet:
        from wingman_day1.infrastructure.fake_upgrade import demo_upgrades
        from wingman_day1.infrastructure.fake_upgrade_script import (
            default_upgrade_file,
            load_upgrade_script,
        )

        return demo_upgrades(load_upgrade_script(default_upgrade_file()), clock=clock)
    workflow = HttpUpgradeWorkflow(
        base_url=settings.workflows_api_url,
        verify=settings.workflows_tls_verify,
        timeout_seconds=settings.workflows_timeout_seconds,
        targets_timeout_seconds=settings.workflows_targets_timeout_seconds,
        metrics=metrics,
    )
    closers.append(workflow.aclose)
    return workflow


def upgrade_service(
    settings: Day1Settings,
    workflow: UpgradeWorkflow | None,
    clusters: ClusterService,
    cache: TtlCache,
) -> UpgradeService | None:
    """The upgrade use case while ``DAY1_UPGRADES`` is on; ``None`` (the routes' 501) otherwise.

    The fleet's list reads through a short cache (as Inventory's runs); a
    cluster's own run is read uncached.
    """
    if not settings.day1_upgrades or workflow is None:
        return None
    ttl = min(settings.day1_cache_ttl_seconds, FLEET_RUNS_TTL_SECONDS)
    return UpgradeService(
        workflow, clusters, cached=CachedUpgradeWorkflow(workflow, cache, ttl=ttl)
    )
