"""The MCE hubs' part of the composition root: live status and the nodes view.

Both read the hubs and are built only with one (``CLUSTER_STATUS_ENABLED``,
or the fake fleet's MCE; ADR-0038, ADR-0041). A KV cluster's create
(ADR-0069) reads a seed's InfraEnvs through live status while it is on.
"""

from __future__ import annotations

from typing import Final

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.application.clusters import ClusterService
from wingman_day1.application.nodes import NodeService
from wingman_day1.application.status import StatusService
from wingman_day1.domain.names import HostedClusterNaming
from wingman_day1.infrastructure.cached_hub import CachedHubApi
from wingman_day1.infrastructure.cached_workflows import CachedUninstallWorkflow
from wingman_day1.integrations.server_scan import compose as server_scan
from wingman_day1.integrations.server_scan.ports import ServerInventory
from wingman_day1.ports import UninstallWorkflow
from wingman_day1.settings import Day1Settings

RUNS_TTL_SECONDS: Final = 10.0
"""The longest an uninstall run's status is cached: the web polls a running one."""


def node_service(
    settings: Day1Settings,
    hub: CachedHubApi | None,
    clusters: ClusterService,
    *,
    inventory: ServerInventory | None,
    uninstall: UninstallWorkflow | None,
    cache: TtlCache,
    ttl: float,
) -> NodeService | None:
    """A cluster's nodes and their uninstall, with a hub; ``None`` without (the routes' 501)."""
    if hub is None:
        return None
    runs_ttl = min(ttl, RUNS_TTL_SECONDS)
    return NodeService(
        hub,
        clusters,
        inventory=inventory,
        ui_url=server_scan.server_scan_ui(settings),
        workflows=(
            CachedUninstallWorkflow(uninstall, cache, ttl=runs_ttl)
            if uninstall is not None
            else None
        ),
        infraenv_namespace=settings.mce_infraenv_namespace or None,
    )


def status_service(
    settings: Day1Settings,
    hub: CachedHubApi | None,
    clusters: ClusterService,
    *,
    naming: HostedClusterNaming,
    infra_envs: CachedHubApi | None,
) -> StatusService | None:
    """Live status with a hub; ``None`` without (the routes' 501)."""
    if hub is None:
        return None
    return StatusService(
        hub,
        clusters,
        naming=naming,
        infraenv_namespace=settings.mce_infraenv_namespace or None,
        infra_envs=infra_envs,
    )
