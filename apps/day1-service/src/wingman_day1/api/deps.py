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
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.application.nodes import NodeService
from wingman_day1.application.sites import SiteCatalog
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.application.status import StatusService
from wingman_day1.application.sync import SyncService
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
    auth: AuthService
    repos: Mapping[RepoKey, RepoReads]
    machine_configs: MachineConfigService
    status: StatusService | None = None
    """``None`` when ``CLUSTER_STATUS_ENABLED`` is off: those routes answer 501."""
    webhook_secret: str | None = None
    """``None`` when ``GITLAB_WEBHOOK_SECRET`` is empty: the webhook route answers 404."""
    status_poll_seconds: float = 30.0
    delete_workflow: ClusterDeleteWorkflow | None = None
    """``None`` until the delete-cluster workflow exists: its routes answer 501 (ADR-0033)."""
    nodes: NodeService | None = None
    """``None`` when server-scan is not configured: the nodes routes answer 501 (ADR-0038)."""


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
    "Cluster nodes are not available in this deployment: server-scan is not configured "
    "(SERVER_SCAN_URL)."
)


def node_service(context: Annotated[Day1Context, Depends(day1_context)]) -> NodeService:
    """The cluster nodes use case, or 501 when server-scan is not configured (ADR-0038)."""
    if context.nodes is None:
        raise FeatureDisabled(NODES_NOT_AVAILABLE)
    return context.nodes


Context = Annotated[Day1Context, Depends(day1_context)]
DeleteWorkflow = Annotated[ClusterDeleteWorkflow, Depends(delete_workflow)]
Nodes = Annotated[NodeService, Depends(node_service)]
Status = Annotated[StatusService, Depends(status_service)]
