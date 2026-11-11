"""``/api/day1/clusters``: hosted clusters, their status, history and drift.

Reads need a session (``CurrentUser``); every change needs an admin
(``AdminUser``) and is a merge request. Static paths come before
``/{name}`` so a cluster can never shadow them.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Path, Query
from fastapi.responses import PlainTextResponse, StreamingResponse

from wingman_core.domain.errors import GitError
from wingman_core.web.auth import AdminUser, CurrentUser
from wingman_day1.api.deps import Context, DeleteWorkflow, Nodes, Status
from wingman_day1.api.v1.schemas import (
    BulkStatusIn,
    ClusterDetailOut,
    ClusterDriftOut,
    ClusterLiveStatusOut,
    ClusterNodesOut,
    ClusterStatusOut,
    CommitOut,
    CreateClusterIn,
    DeleteWorkflowOut,
    DriftSummaryItemOut,
    ModifyClusterIn,
    MRDetailOut,
    PreviewOut,
    StartDeleteWorkflowIn,
    SyncIn,
    SyncPreviewIn,
    SyncPreviewOut,
    UninstallNodeIn,
    WorkflowRunOut,
    change_out,
    cluster_detail,
)
from wingman_day1.application.approvals import RepoKey
from wingman_day1.application.clusters import CreateCluster
from wingman_day1.domain.errors import Day1Error
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.segments_manager import segments_manager_links

router = APIRouter(prefix="/api/day1/clusters", tags=["clusters"])

Site = Annotated[str | None, Query(max_length=63, description="Site folder")]
Mce = Annotated[str | None, Query(max_length=63, description="MCE folder")]
RequiredMce = Annotated[str, Query(min_length=1, max_length=63, description="MCE folder")]
ServerId = Annotated[
    str,
    Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$", description="server-scan id"),
]


def _create(body: CreateClusterIn) -> CreateCluster:
    return CreateCluster(
        name=body.name,
        site=body.site,
        mce=body.mce,
        spec_name=body.spec_name,
        spec_version=body.spec_version,
        variables=body.variables,
        addon_overrides=body.addon_overrides or {},
    )


async def _ref(context: Context, name: str, site: str | None, mce: str | None) -> ClusterRef:
    return await context.clusters.locate(name, site=site, mce=mce)


# ── Collection routes ────────────────────────────────────────────────────────


@router.get("")
async def list_clusters(context: Context, user: CurrentUser) -> list[ClusterStatusOut]:
    """Every cluster file; off-convention and unparsable files are flagged, not hidden."""
    return [ClusterStatusOut.of(c) for c in await context.clusters.clusters()]


@router.get("/drift-summary")
async def drift_summary(context: Context, user: CurrentUser) -> list[DriftSummaryItemOut]:
    """Drift of every cluster; a cluster whose drift is unknown says so (``state``, ``error``)."""
    return [DriftSummaryItemOut.of(d) for d in await context.drift.summary()]


@router.post("/bulk-status")
async def bulk_status(
    body: BulkStatusIn, user: CurrentUser, status: Status
) -> dict[str, ClusterLiveStatusOut]:
    """Live status of many clusters; each failure is in its entry's ``error``."""
    results = await status.statuses([(c.name, c.mce) for c in body.clusters])
    return {name: ClusterLiveStatusOut.of(s) for name, s in results.items()}


@router.post("/preview")
async def preview_cluster(body: CreateClusterIn, context: Context, user: AdminUser) -> PreviewOut:
    """Exactly the file a create would commit, after every check a create runs."""
    rendered = await context.clusters.preview(_create(body))
    return PreviewOut(yaml=rendered.content, path=str(rendered.ref.path))


@router.post("", status_code=201)
async def create_cluster(body: CreateClusterIn, context: Context, user: AdminUser) -> MRDetailOut:
    """Open the MR that adds the cluster's file."""
    result = await context.clusters.create(_create(body), user=user)
    return change_out(RepoKey.DAY1, result.merge_request)


# ── One cluster ──────────────────────────────────────────────────────────────


@router.get("/{name}/status")
async def cluster_status(
    name: str, mce: RequiredMce, user: CurrentUser, status: Status
) -> ClusterLiveStatusOut:
    """The HostedCluster and NodePools on the MCE hub (501 when status is off)."""
    return ClusterLiveStatusOut.of(await status.status(name, mce))


@router.get("/{name}/status/stream")
async def stream_cluster_status(
    name: str, mce: RequiredMce, user: CurrentUser, status: Status, context: Context
) -> StreamingResponse:
    """Server-sent events: the live status now, then every ``status_poll_seconds``."""

    async def events() -> AsyncIterator[str]:
        try:
            async for live in status.watch(name, mce, interval=context.status_poll_seconds):
                yield f"data: {ClusterLiveStatusOut.of(live).model_dump_json()}\n\n"
        except (Day1Error, GitError) as exc:
            yield f"data: {json.dumps({'error': f'{type(exc).__name__}: {exc}'})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{name}/history")
async def cluster_history(
    name: str, context: Context, user: CurrentUser, site: Site = None, mce: Mce = None
) -> list[CommitOut]:
    """Commits that changed the cluster's file."""
    ref = await _ref(context, name, site, mce)
    return [CommitOut.of(c) for c in await context.clusters.history(ref)]


@router.get("/{name}/current-yaml", response_class=PlainTextResponse)
async def cluster_current_yaml(
    name: str, context: Context, user: CurrentUser, site: Site = None, mce: Mce = None
) -> str:
    """The file's text at the default branch."""
    ref = await _ref(context, name, site, mce)
    return (await context.clusters.get(ref)).content


@router.get("/{name}/drift")
async def cluster_drift(
    name: str, context: Context, user: CurrentUser, site: Site = None, mce: Mce = None
) -> ClusterDriftOut:
    """The cluster against its flavor: locked values the file does not hold, missing add-ons."""
    ref = await _ref(context, name, site, mce)
    return ClusterDriftOut.of(await context.drift.for_cluster(ref))


@router.post("/{name}/sync/preview")
async def sync_preview(
    name: str,
    body: SyncPreviewIn,
    context: Context,
    user: AdminUser,
    site: Site = None,
    mce: Mce = None,
) -> SyncPreviewOut:
    """What syncing the cluster to its flavor would write, remove and reboot (ADR-0037)."""
    ref = await _ref(context, name, site, mce)
    hardware = {c.nodepool: c.hardware for c in body.hardware}
    return SyncPreviewOut.of(await context.sync.preview(ref, hardware=hardware))


@router.post("/{name}/sync", status_code=201)
async def sync_cluster(
    name: str,
    body: SyncIn,
    context: Context,
    user: AdminUser,
    site: Site = None,
    mce: Mce = None,
) -> MRDetailOut:
    """Open one day1 MR that sets every locked value the file does not hold to the flavor's."""
    ref = await _ref(context, name, site, mce)
    result = await context.sync.sync(
        ref,
        last_commit_id=body.last_commit_id,
        spec_version=body.spec_version,
        hardware={c.nodepool: c.hardware for c in body.hardware},
        confirm_removals=[(r.nodepool, r.name) for r in body.confirm_removals],
        user=user,
    )
    return change_out(RepoKey.DAY1, result.provision.merge_request)


@router.get("/{name}")
async def cluster(
    name: str, context: Context, user: CurrentUser, site: Site = None, mce: Mce = None
) -> ClusterDetailOut:
    """The cluster's file, values and naming. ``site``/``mce`` are optional: names are unique."""
    ref = await _ref(context, name, site, mce)
    found = await context.clusters.get(ref)
    ui = context.segments_manager_ui_url
    return cluster_detail(
        found,
        gitlab_url=await context.clusters.web_url(ref),
        mce_default_mastertag=await context.sites.default_mastertag(ref.site, ref.mce),
        segments_manager=segments_manager_links(ui, ref.name) if ui else None,
    )


@router.patch("/{name}")
async def modify_cluster(
    name: str,
    body: ModifyClusterIn,
    context: Context,
    user: AdminUser,
    site: Site = None,
    mce: Mce = None,
) -> MRDetailOut:
    """Open the MR that replaces the file; automation-owned keys must stay as they are."""
    ref = await _ref(context, name, site, mce)
    result = await context.clusters.modify(
        ref,
        body.updated_yaml,
        user=user,
        summary=body.change_summary,
        last_commit_id=body.last_commit_id,
    )
    return change_out(RepoKey.DAY1, result.merge_request)


@router.get("/{name}/delete-workflow")
async def delete_workflow_state(
    name: str,
    context: Context,
    user: CurrentUser,
    workflow: DeleteWorkflow,
    site: Site = None,
    mce: Mce = None,
) -> DeleteWorkflowOut:
    """The newest delete-cluster run (501 until the workflow exists, ADR-0033)."""
    ref = await _ref(context, name, site, mce)
    run = await workflow.latest_run(ref)
    return DeleteWorkflowOut(run=WorkflowRunOut.of(run) if run else None)


@router.post("/{name}/delete-workflow", status_code=202)
async def start_delete_workflow(
    name: str,
    body: StartDeleteWorkflowIn,
    context: Context,
    user: AdminUser,
    workflow: DeleteWorkflow,
    site: Site = None,
    mce: Mce = None,
) -> WorkflowRunOut:
    """Start the delete-cluster workflow (501 until it exists, ADR-0033)."""
    ref = await _ref(context, name, site, mce)
    return WorkflowRunOut.of(await workflow.start(ref, requested_by=user))


@router.get("/{name}/nodes")
async def cluster_nodes(
    name: str,
    context: Context,
    user: CurrentUser,
    nodes: Nodes,
    site: Site = None,
    mce: Mce = None,
) -> ClusterNodesOut:
    """The servers server-scan places in the cluster, with their newest uninstall run (ADR-0038)."""
    ref = await _ref(context, name, site, mce)
    return ClusterNodesOut.of(await nodes.nodes(ref))


@router.post("/{name}/nodes/{server_id}/uninstall", status_code=202)
async def uninstall_node(
    name: str,
    server_id: ServerId,
    body: UninstallNodeIn,
    context: Context,
    user: AdminUser,
    nodes: Nodes,
    site: Site = None,
    mce: Mce = None,
) -> WorkflowRunOut:
    """Start the platform's uninstall-server-from-hc workflow on one node (ADR-0038)."""
    ref = await _ref(context, name, site, mce)
    run = await nodes.uninstall(ref, server_id, server_name=body.server_name, user=user)
    return WorkflowRunOut.of(run)


@router.delete("/{name}")
async def delete_cluster(
    name: str,
    context: Context,
    user: AdminUser,
    site: Site = None,
    mce: Mce = None,
    last_commit_id: Annotated[str | None, Query(min_length=7, max_length=64)] = None,
) -> MRDetailOut:
    """Open the MR that removes the file."""
    ref = await _ref(context, name, site, mce)
    result = await context.clusters.delete(ref, user=user, last_commit_id=last_commit_id)
    return change_out(RepoKey.DAY1, result.merge_request)
