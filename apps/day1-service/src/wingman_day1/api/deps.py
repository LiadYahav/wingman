"""Route dependencies: they only retrieve what ``main.py`` built (server-scan's pattern).

``main.create_app`` puts one :class:`Day1Context` on ``app.state.day1``; tests
build their own with fakes. Nothing here constructs a client.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from wingman_core.web.errors import FeatureDisabled
from wingman_day1.application.agent_labels import AgentLabelsService
from wingman_day1.application.approvals import ApprovalService, RepoKey
from wingman_day1.application.audit import AuditService
from wingman_day1.application.auth import AuthService
from wingman_day1.application.clusters import ClusterService
from wingman_day1.application.drift import DriftService
from wingman_day1.application.imports import ImportService
from wingman_day1.application.inventory import InventoryService
from wingman_day1.application.kv_clusters import KvClusterService
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.application.network import NetworkService
from wingman_day1.application.nodes import NodeService
from wingman_day1.application.placement import PlacementService
from wingman_day1.application.quick_links import QuickLinksService
from wingman_day1.application.rollouts import RolloutService
from wingman_day1.application.scale import ScaleService
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.application.status import StatusService
from wingman_day1.application.sync import SyncService
from wingman_day1.application.upgrades import UpgradeService
from wingman_day1.domain.platforms import Platform
from wingman_day1.ports import ClusterDeleteWorkflow, RepoReads


@dataclass(frozen=True, slots=True)
class Day1Context:
    """Every use case the routes call, built once per app."""

    clusters: ClusterService
    sites: SiteCatalog
    specs: SpecCatalog
    approvals: ApprovalService
    audit: AuditService
    drift: DriftService
    imports: ImportService
    sync: SyncService
    rollouts: RolloutService
    """A flavor's new version, one MR per cluster (ADR-0044)."""
    auth: AuthService
    repos: Mapping[RepoKey, RepoReads]
    machine_configs: MachineConfigService
    network: NetworkService
    """A cluster's network from its file; segments-manager adds the EPG when it is configured."""
    status: StatusService | None = None
    """``None`` when ``CLUSTER_STATUS_ENABLED`` is off: those routes answer 501."""
    webhook_secret: str | None = None
    """``None`` when ``GITLAB_WEBHOOK_SECRET`` is empty: the webhook route answers 404."""
    status_poll_seconds: float = 30.0
    delete_workflow: ClusterDeleteWorkflow | None = None
    """``None`` until the delete-cluster workflow exists: its routes answer 501 (ADR-0033)."""
    nodes: NodeService | None = None
    """``None`` when live status (the MCE hubs) is off: the nodes routes answer 501."""
    segments_manager_ui_url: str | None = None
    """``None`` when neither ``SEGMENTS_MANAGER_UI_URL`` nor ``SEGMENTS_MANAGER_URL`` is set:
    a cluster carries no link to segments-manager."""
    placement: PlacementService | None = None
    """Always built by ``main`` (ADR-0050: placement runs with live reads off too); a
    context built without one answers 501."""
    quick_links: QuickLinksService | None = None
    """The Quick Links page (ADR-0052); ``main`` always builds it."""
    upgrades: UpgradeService | None = None
    """``None`` when ``DAY1_UPGRADES`` is off: the upgrade routes answer 501 (ADR-0055)."""
    inventory: InventoryService | None = None
    """Inventory Management (ADR-0057); ``None`` when ``SERVER_SCAN_URL`` is empty: 501."""
    scale: ScaleService | None = None
    """``None`` when Scale is off (``DAY1_SCALE_NODEPOOLS=false``, or no orchestrator): the
    scale routes answer 501 (ADR-0062)."""
    agent_labels: AgentLabelsService | None = None
    """A cluster's excluded Agent labels MR (ADR-0065); without keys its routes answer 501."""
    platforms: tuple[Platform, ...] = ()
    """segments-manager's and server-scan's own UIs, the sidebar's links out (ADR-0067)."""
    kv_clusters: KvClusterService | None = None
    """A new KV cluster on a seed (ADR-0069); ``main`` always builds it."""


def day1_context(request: Request) -> Day1Context:
    """The app's context."""
    return request.app.state.day1


def status_service(context: Annotated[Day1Context, Depends(day1_context)]) -> StatusService:
    """The status use case, or 501 when live status is switched off."""
    if context.status is None:
        raise FeatureDisabled(
            "Live cluster status is disabled in this deployment (CLUSTER_STATUS_ENABLED=false)."
        )
    return context.status


DELETE_WORKFLOW_NOT_AVAILABLE = (
    "The delete-cluster workflow is not available yet. Until it exists, deleting a cluster "
    "opens an MR that removes its file, and the cluster's network segment is not released."
)


def delete_workflow(
    context: Annotated[Day1Context, Depends(day1_context)],
) -> ClusterDeleteWorkflow:
    """The delete-cluster workflow, or 501 while it does not exist (ADR-0033)."""
    if context.delete_workflow is None:
        raise FeatureDisabled(DELETE_WORKFLOW_NOT_AVAILABLE)
    return context.delete_workflow


NODES_NOT_AVAILABLE = (
    "Cluster nodes are not available in this deployment: they are read from the MCE, and "
    "live cluster status is off (CLUSTER_STATUS_ENABLED=false)."
)


def node_service(context: Annotated[Day1Context, Depends(day1_context)]) -> NodeService:
    """The cluster nodes use case, or 501 when the MCE hubs cannot be read (ADR-0038)."""
    if context.nodes is None:
        raise FeatureDisabled(NODES_NOT_AVAILABLE)
    return context.nodes


PLACEMENT_NOT_AVAILABLE = "MCE placement is not set up in this deployment."


def placement_service(context: Annotated[Day1Context, Depends(day1_context)]) -> PlacementService:
    """The placement use case (``main`` always builds it; a bare context has none: 501)."""
    if context.placement is None:
        raise FeatureDisabled(PLACEMENT_NOT_AVAILABLE)
    return context.placement


def quick_links_service(
    context: Annotated[Day1Context, Depends(day1_context)],
) -> QuickLinksService:
    """The Quick Links use case (a context built without one has none: 501)."""
    if context.quick_links is None:
        raise FeatureDisabled("Quick Links is not set up in this deployment.")
    return context.quick_links


UPGRADES_NOT_AVAILABLE = (
    "Upgrades are not turned on in this deployment (DAY1_UPGRADES=false): a cluster's "
    "version changes by editing its file."
)


def upgrade_service(context: Annotated[Day1Context, Depends(day1_context)]) -> UpgradeService:
    """The upgrade use case, or 501 when ``DAY1_UPGRADES`` is off (ADR-0055)."""
    if context.upgrades is None:
        raise FeatureDisabled(UPGRADES_NOT_AVAILABLE)
    return context.upgrades


SCALE_NOT_AVAILABLE = (
    "Scaling NodePools is off in this deployment (DAY1_SCALE_NODEPOOLS=false, or no "
    "WORKFLOWS_API_URL): a NodePool's replicas change by editing its cluster file."
)


def scale_service(context: Annotated[Day1Context, Depends(day1_context)]) -> ScaleService:
    """The scale use case, or 501 when Scale is off (ADR-0062)."""
    if context.scale is None:
        raise FeatureDisabled(SCALE_NOT_AVAILABLE)
    return context.scale


AGENT_LABELS_NOT_SET = (
    "This deployment excludes no Agent labels: DAY1_EXCLUDED_AGENT_LABELS is empty (ADR-0065)."
)


def agent_labels_service(
    context: Annotated[Day1Context, Depends(day1_context)],
) -> AgentLabelsService:
    """A cluster's excluded Agent labels merge request, or 501 when the setting is empty."""
    if context.agent_labels is None or not context.agent_labels.labels:
        raise FeatureDisabled(AGENT_LABELS_NOT_SET)
    return context.agent_labels


INVENTORY_NOT_AVAILABLE = (
    "Inventory Management is not set up in this deployment: it counts server-scan's servers, "
    "and SERVER_SCAN_URL is empty."
)


def inventory_service(
    context: Annotated[Day1Context, Depends(day1_context)],
) -> InventoryService:
    """Inventory Management's use case, or 501 when server-scan is not configured (ADR-0057)."""
    if context.inventory is None:
        raise FeatureDisabled(INVENTORY_NOT_AVAILABLE)
    return context.inventory


def kv_cluster_service(
    context: Annotated[Day1Context, Depends(day1_context)],
) -> KvClusterService:
    """The KV cluster create (``main`` always builds it; a bare context has none: 501)."""
    if context.kv_clusters is None:
        raise FeatureDisabled("Creating a KV cluster is not set up in this deployment.")
    return context.kv_clusters


AgentLabels = Annotated[AgentLabelsService, Depends(agent_labels_service)]
Context = Annotated[Day1Context, Depends(day1_context)]
DeleteWorkflow = Annotated[ClusterDeleteWorkflow, Depends(delete_workflow)]
Inventory = Annotated[InventoryService, Depends(inventory_service)]
KvClusters = Annotated[KvClusterService, Depends(kv_cluster_service)]
Nodes = Annotated[NodeService, Depends(node_service)]
Placements = Annotated[PlacementService, Depends(placement_service)]
QuickLinks = Annotated[QuickLinksService, Depends(quick_links_service)]
Scale = Annotated[ScaleService, Depends(scale_service)]
Status = Annotated[StatusService, Depends(status_service)]
Upgrades = Annotated[UpgradeService, Depends(upgrade_service)]
