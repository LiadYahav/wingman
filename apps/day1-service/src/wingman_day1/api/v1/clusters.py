"""``/api/day1/clusters``: hosted clusters, their status, history and drift.

Reads need a session (``CurrentUser``), but a cluster's nodes, the servers
it runs on, need an admin (ADR-0038, amended 2026-11-23); every change needs
an admin (``AdminUser``). A create starts the provision-cluster workflow
(ADR-0042); an edit or a delete is a merge request. Static paths come before
``/{name}`` so a cluster can never shadow them. Live status has its own module,
``cluster_status.py``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query
from fastapi.responses import PlainTextResponse

from wingman_core.web.auth import AdminUser, CurrentUser
from wingman_day1.api.deps import Context, DeleteWorkflow, Nodes
from wingman_day1.api.v1.cluster_network_schemas import ClusterNetworkOut
from wingman_day1.api.v1.cluster_nodes_schemas import ClusterNodesOut, UninstallNodeIn
from wingman_day1.api.v1.cluster_sync_schemas import SyncIn, SyncOut, SyncPreviewIn, SyncPreviewOut
from wingman_day1.api.v1.cluster_workflows_schemas import (
    DeleteWorkflowOut,
    ProvisionRunOut,
    StartDeleteWorkflowIn,
)
from wingman_day1.api.v1.clusters_schemas import (
    ClusterDetailOut,
    ClusterStatusOut,
    CreateClusterIn,
    DriftSummaryItemOut,
    ModifyClusterIn,
    NameSuggestionOut,
    PreviewOut,
    cluster_detail,
)
from wingman_day1.api.v1.scale_schemas import HeldReplicasOut
from wingman_day1.api.v1.schemas import (
    ClusterDriftOut,
    CommitOut,
    MRDetailOut,
    WorkflowRunOut,
    change_out,
)
from wingman_day1.api.v1.visible import cluster_ref
from wingman_day1.application.approvals import RepoKey
from wingman_day1.application.clusters import CreateCluster
from wingman_day1.application.drift import ClusterDrift
from wingman_day1.application.upgrades import upgrade_hints
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.placement import Choice
from wingman_day1.domain.visibility import require_seen, seen
from wingman_day1.integrations.segments_manager.domain.links import segments_manager_links

router = APIRouter(prefix="/api/day1/clusters", tags=["clusters"])


def _ref_of(drift: ClusterDrift) -> ClusterRef:
    return drift.ref


Site = Annotated[str | None, Query(max_length=63, description="Site folder")]
Mce = Annotated[str | None, Query(max_length=63, description="MCE folder")]
RequiredMce = Annotated[str, Query(min_length=1, max_length=63, description="MCE folder")]
RequiredSite = Annotated[str, Query(min_length=1, max_length=63, description="Site folder")]
Flavor = Annotated[str, Query(min_length=1, max_length=63, description="Flavor (spec) name")]
NewClusterName = Annotated[
    str,
    Path(
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$",
        description="The new cluster file's stem",
    ),
]
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
        placement=(
            Choice(pick=body.placement.pick, reason=body.placement.reason)
            if body.placement is not None
            else None
        ),
    )


# ── Collection routes ────────────────────────────────────────────────────────


@router.get("")
async def list_clusters(context: Context, user: CurrentUser) -> list[ClusterStatusOut]:
    """Every cluster file; off-convention and unparsable files are flagged, not hidden.

    Each says its kind; a viewer's list has no KV cluster (ADR-0067). While upgrades
    are on, each says the newer release its MCE offers, if any.
    """
    clusters = seen(user, await context.clusters.clusters(), lambda c: c.ref)
    hints = await upgrade_hints(context.sites, clusters) if context.upgrades is not None else {}
    return [ClusterStatusOut.of(c, upgrade_available=hints.get(c.ref)) for c in clusters]


@router.get("/drift-summary")
async def drift_summary(context: Context, user: CurrentUser) -> list[DriftSummaryItemOut]:
    """Drift of every cluster a user may know of; unknown drift says so (``state``, ``error``)."""
    return [DriftSummaryItemOut.of(d) for d in seen(user, await context.drift.summary(), _ref_of)]


@router.get("/name-suggestion")
async def name_suggestion(
    context: Context, user: CurrentUser, site: RequiredSite, mce: RequiredMce, flavor: Flavor
) -> NameSuggestionOut:
    """A free name for a new cluster from ``flavor``: ``ocp4-<env>-<flavor>-<site>-<letter>``.

    The env is the MCE's, the letter the first no cluster or open create MR
    has (ADR-0040). ``name`` is ``null``, with ``problems``, when there is none.
    """
    return NameSuggestionOut.of(
        await context.clusters.suggest_name(site=site, mce=mce, flavor=flavor)
    )


@router.post("/preview")
async def preview_cluster(body: CreateClusterIn, context: Context, user: AdminUser) -> PreviewOut:
    """Exactly the file a create hands provision-cluster, after every check a create runs."""
    rendered = await context.clusters.preview(_create(body))
    return PreviewOut(yaml=rendered.content, path=str(rendered.ref.path))


@router.post("", status_code=202)
async def create_cluster(
    body: CreateClusterIn, context: Context, user: AdminUser
) -> ProvisionRunOut:
    """Start the provision-cluster workflow with the new file (ADR-0042): 202 with the run.

    The workflow reserves the segment and opens the merge request; a person merges it.
    """
    return ProvisionRunOut.of(await context.clusters.create(_create(body), user=user))


# ── One cluster ──────────────────────────────────────────────────────────────


@router.get("/{name}/history")
async def cluster_history(
    name: str, context: Context, user: CurrentUser, site: Site = None, mce: Mce = None
) -> list[CommitOut]:
    """Commits that changed the cluster's file."""
    ref = await cluster_ref(context, user, name, site, mce)
    return [CommitOut.of(c) for c in await context.clusters.history(ref)]


@router.get("/{name}/current-yaml", response_class=PlainTextResponse)
async def cluster_current_yaml(
    name: str, context: Context, user: CurrentUser, site: Site = None, mce: Mce = None
) -> str:
    """The file's text at the default branch."""
    ref = await cluster_ref(context, user, name, site, mce)
    return (await context.clusters.get(ref)).content


@router.get("/{name}/drift")
async def cluster_drift(
    name: str, context: Context, user: CurrentUser, site: Site = None, mce: Mce = None
) -> ClusterDriftOut:
    """The cluster against its flavor: locked values the file does not hold, missing add-ons."""
    ref = await cluster_ref(context, user, name, site, mce)
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
    ref = await cluster_ref(context, user, name, site, mce)
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
) -> SyncOut:
    """Open one day1 MR that sets every locked value the file does not hold to the flavor's."""
    ref = await cluster_ref(context, user, name, site, mce)
    result = await context.sync.sync(
        ref,
        last_commit_id=body.last_commit_id,
        spec_version=body.spec_version,
        hardware={c.nodepool: c.hardware for c in body.hardware},
        confirm_removals=[(r.nodepool, r.name) for r in body.confirm_removals],
        user=user,
    )
    opened = change_out(RepoKey.DAY1, result.provision.merge_request)
    held = [HeldReplicasOut.of(h) for h in result.plan.held_replicas]
    return SyncOut(**opened.model_dump(), held_replicas=held)


@router.get("/{name}")
async def cluster(
    name: str, context: Context, user: CurrentUser, site: Site = None, mce: Mce = None
) -> ClusterDetailOut:
    """The cluster's file, values and naming. ``site``/``mce`` are optional: names are unique."""
    ref = await cluster_ref(context, user, name, site, mce)
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
    ref = await cluster_ref(context, user, name, site, mce)
    result = await context.clusters.modify(
        ref,
        body.updated_yaml,
        user=user,
        summary=body.change_summary,
        last_commit_id=body.last_commit_id,
    )
    return change_out(RepoKey.DAY1, result.merge_request)


@router.get("/{name}/provision-run")
async def provision_run(
    name: NewClusterName, context: Context, user: CurrentUser
) -> ProvisionRunOut:
    """The cluster's provision-cluster run (ADR-0042), read by its id.

    The cluster has no file on main until the workflow's merge request is
    merged, so ``name`` is the new file's stem, not a cluster day1 can read.
    404 when the orchestrator has no run, or when a viewer names a KV cluster.
    """
    require_seen(user, name, mce="")
    return ProvisionRunOut.of(await context.clusters.provision_run(name))


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
    ref = await cluster_ref(context, user, name, site, mce)
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
    ref = await cluster_ref(context, user, name, site, mce)
    return WorkflowRunOut.of(await workflow.start(ref, requested_by=user))


@router.get("/{name}/network")
async def cluster_network(
    name: str, context: Context, user: CurrentUser, site: Site = None, mce: Mce = None
) -> ClusterNetworkOut:
    """The cluster's VLAN and segment from its file, with the EPG from segments-manager.

    What segments-manager says that disagrees with the file is in ``problems``
    (ADR-0039). segments-manager off: ``ledger`` is ``null``; failing: also
    ``ledger_error``. Neither fails the read, and the MCE is never asked.
    """
    ref = await cluster_ref(context, user, name, site, mce)
    return ClusterNetworkOut.of(await context.network.network(ref))


@router.get("/{name}/nodes")
async def cluster_nodes(
    name: str,
    context: Context,
    user: AdminUser,
    nodes: Nodes,
    site: Site = None,
    mce: Mce = None,
) -> ClusterNodesOut:
    """The servers server-scan places in the cluster, with their newest uninstall run (ADR-0038).

    Admins only: a viewer never sees a cluster's nodes (403, ADR-0038's 2026-11-23 amendment).
    """
    ref = await cluster_ref(context, user, name, site, mce)
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
    ref = await cluster_ref(context, user, name, site, mce)
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
    confirm: Annotated[str, Query(max_length=63, description="A KV cluster's name, typed")] = "",
) -> MRDetailOut:
    """Open the MR that removes the file. A KV cluster's needs its name as ``confirm`` (422)."""
    ref = await cluster_ref(context, user, name, site, mce)
    result = await context.clusters.delete(
        ref, user=user, last_commit_id=last_commit_id, confirm=confirm
    )
    return change_out(RepoKey.DAY1, result.merge_request)
