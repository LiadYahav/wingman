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
from wingman_day1.application.segments import SegmentsService
from wingman_day1.application.server_scan import ServerScanService
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.application.status import StatusService
from wingman_day1.application.sync import SyncService
from wingman_day1.application.upgrades import UpgradeService
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


def segments_service(context: Annotated[Day1Context, Depends(day1_context)]) -> SegmentsService:
    """The Segments area's use case, or 501 when segments-manager is not configured."""
    if context.segments is None:
        raise FeatureDisabled(SEGMENTS_NOT_AVAILABLE)
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


def server_scan_service(
    context: Annotated[Day1Context, Depends(day1_context)],
) -> ServerScanService:
    """The Server Scan area's use cases, or 501 when server-scan is not configured (ADR-0048)."""
    if context.server_scan is None:
        raise FeatureDisabled(SERVER_SCAN_NOT_AVAILABLE)
    return context.server_scan


Context = Annotated[Day1Context, Depends(day1_context)]
DeleteWorkflow = Annotated[ClusterDeleteWorkflow, Depends(delete_workflow)]
Inventory = Annotated[InventoryService, Depends(inventory_service)]
Nodes = Annotated[NodeService, Depends(node_service)]
Placements = Annotated[PlacementService, Depends(placement_service)]
QuickLinks = Annotated[QuickLinksService, Depends(quick_links_service)]
Segments = Annotated[SegmentsService, Depends(segments_service)]
ServerScan = Annotated[ServerScanService, Depends(server_scan_service)]
Status = Annotated[StatusService, Depends(status_service)]
Upgrades = Annotated[UpgradeService, Depends(upgrade_service)]
