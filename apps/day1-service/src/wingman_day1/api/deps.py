"""Route dependencies: they only retrieve what ``main.py`` built (server-scan's pattern).

``main.create_app`` puts one :class:`Day1Context` on ``app.state.day1``; tests
build their own with fakes. Nothing here constructs a client.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
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
from wingman_day1.domain.platforms import Platforms
from wingman_day1.integrations.segments_manager.application.segments import SegmentsService
from wingman_day1.integrations.server_scan.application.area import ServerScanService
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
    segments: SegmentsService | None = None
    """The Segments area (ADR-0047); ``None`` when ``SEGMENTS_MANAGER_URL`` is empty: 501."""
    upgrades: UpgradeService | None = None
    """``None`` when ``DAY1_UPGRADES`` is off: the upgrade routes answer 501 (ADR-0055)."""
    inventory: InventoryService | None = None
    """Inventory Management (ADR-0057); ``None`` when ``SERVER_SCAN_URL`` is empty: 501."""
    server_scan: ServerScanService | None = None
    """The Server Scan area (ADR-0048); ``None`` when ``SERVER_SCAN_URL`` is empty: 501."""
    scale: ScaleService | None = None
    """``None`` when ``DAY1_SCALE_NODEPOOLS`` is off: the scale routes answer 501 (ADR-0062)."""
    agent_labels: AgentLabelsService | None = None
    """A cluster's excluded Agent labels MR (ADR-0065); without keys its routes answer 501."""
    platforms: Platforms = field(default_factory=Platforms)
    """segments-manager and server-scan for the top bar, and whether each one's area is on
    (2026-11-23): an area that is off answers 501, as one whose system is not configured."""


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


SEGMENTS_NOT_AVAILABLE = "Segments is not set up in this deployment: SEGMENTS_MANAGER_URL is empty."


SEGMENTS_AREA_OFF = (
    "The Segments area is off in this deployment (DAY1_SEGMENTS_AREA=false): segments-manager "
    "stays apart from Wingman, and the top bar links to its own UI."
)


def segments_service(context: Annotated[Day1Context, Depends(day1_context)]) -> SegmentsService:
    """The Segments area's use case, or 501 when segments-manager is not configured or it is off."""
    if context.segments is None:
        raise FeatureDisabled(SEGMENTS_NOT_AVAILABLE)
    if not context.platforms.area("segments"):
        raise FeatureDisabled(SEGMENTS_AREA_OFF, details={"setting": "DAY1_SEGMENTS_AREA"})
    return context.segments


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
    "Scaling NodePools is not turned on in this deployment (DAY1_SCALE_NODEPOOLS=false): "
    "a NodePool's replicas change by editing its cluster file."
)


def scale_service(context: Annotated[Day1Context, Depends(day1_context)]) -> ScaleService:
    """The scale use case, or 501 when ``DAY1_SCALE_NODEPOOLS`` is off (ADR-0062)."""
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


SERVER_SCAN_NOT_AVAILABLE = (
    "Server Scan is not set up in this deployment: SERVER_SCAN_URL is empty."
)
SERVER_SCAN_AREA_OFF = (
    "The Server Scan area is off in this deployment (DAY1_SERVER_SCAN_AREA=false): server-scan "
    "stays apart from Wingman, and the top bar links to its own UI."
)


def server_scan_service(
    context: Annotated[Day1Context, Depends(day1_context)],
) -> ServerScanService:
    """The Server Scan area's use cases, or 501 when server-scan is not configured or it is off."""
    if context.server_scan is None:
        raise FeatureDisabled(SERVER_SCAN_NOT_AVAILABLE)
    if not context.platforms.area("server-scan"):
        raise FeatureDisabled(SERVER_SCAN_AREA_OFF, details={"setting": "DAY1_SERVER_SCAN_AREA"})
    return context.server_scan


AgentLabels = Annotated[AgentLabelsService, Depends(agent_labels_service)]
Context = Annotated[Day1Context, Depends(day1_context)]
DeleteWorkflow = Annotated[ClusterDeleteWorkflow, Depends(delete_workflow)]
Inventory = Annotated[InventoryService, Depends(inventory_service)]
Nodes = Annotated[NodeService, Depends(node_service)]
Placements = Annotated[PlacementService, Depends(placement_service)]
QuickLinks = Annotated[QuickLinksService, Depends(quick_links_service)]
Scale = Annotated[ScaleService, Depends(scale_service)]
Segments = Annotated[SegmentsService, Depends(segments_service)]
ServerScan = Annotated[ServerScanService, Depends(server_scan_service)]
Status = Annotated[StatusService, Depends(status_service)]
Upgrades = Annotated[UpgradeService, Depends(upgrade_service)]
