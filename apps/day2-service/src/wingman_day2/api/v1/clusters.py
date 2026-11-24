"""Clusters, the charts on them, values previews, and the install/update/remove MRs.

``{cluster}`` is a cluster id (``hosted:site1:prod:<mce>:<name>``, ``mce:...``,
``upi:...``, ``hub``) or a bare name that names exactly one destination. The
legacy ``mce`` query parameter is accepted and narrows a bare name.

A viewer knows of the tenants' clusters alone (ADR-0067, ADR-0068): the list
leaves every other destination out, a read names its cluster by its bare name
(an id, ``hub`` or another destination answers what an unknown cluster
answers, ``mce`` is ignored), and the answer names no MCE (``api/v1/visible.py``).
Every read then asks its service by the destination's id.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from wingman_core.web.auth import AdminUser, CurrentUser
from wingman_day2.api.v1.clusters_schemas import (
    BulkBody,
    BulkFailureOut,
    BulkOut,
    ChangeOut,
    ClusterInstalledOut,
    ClusterOut,
    HistoryEntryOut,
    InstallBody,
    MergePreviewBody,
    UpdateBody,
    UpgradeCheckOut,
    ValuesPreviewOut,
)
from wingman_day2.api.v1.dependencies import Services
from wingman_day2.api.v1.schemas import findings
from wingman_day2.api.v1.visible import view_of
from wingman_day2.application.changes import InstallSpec
from wingman_day2.domain.clusters import ClusterKind
from wingman_day2.domain.errors import ChangeRefusedError

router = APIRouter(prefix="/api/day2", tags=["clusters"])

Mce = Query(default=None, description="Legacy: narrows a bare cluster name to one MCE (admins)")


@router.get("/clusters")
async def list_clusters(
    user: CurrentUser,
    day2: Services,
    kind: ClusterKind | None = Query(default=None),
    site: str | None = Query(default=None),
    env: str | None = Query(default=None),
) -> list[ClusterOut]:
    """Every destination from day1 and the team repos; a viewer's, the tenants' clusters."""
    seen = await view_of(day2, user)
    return seen.all_shown(
        [
            ClusterOut.of(s)
            for s in seen.topology.visible_to(user).clusters
            if (kind is None or s.ref.kind is kind)
            and (site is None or s.ref.site == site)
            and (env is None or s.ref.env == env)
        ]
    )


@router.get("/clusters/{cluster}")
async def get_cluster(
    cluster: str, user: CurrentUser, day2: Services, mce: str | None = Mce
) -> ClusterOut:
    """One destination."""
    seen = await view_of(day2, user)
    return seen.shown(ClusterOut.of(seen.destination(cluster, mce)))


@router.get("/clusters/{cluster}/addons")
async def list_cluster_addons(
    cluster: str,
    user: CurrentUser,
    day2: Services,
    mce: str | None = Mce,
    team: str | None = Query(default=None),
) -> ClusterInstalledOut:
    """The charts the platform generates apps for on the cluster, with where each comes from."""
    seen = await view_of(day2, user)
    ref = seen.destination(cluster, mce).ref
    charts = await seen.guarded(day2.installed.for_cluster(ref.id, team=team))
    return seen.shown(ClusterInstalledOut.of(charts))


@router.get("/clusters/{cluster}/addons/{team}/{addon}")
async def get_cluster_addon(
    cluster: str,
    team: str,
    addon: str,
    user: CurrentUser,
    day2: Services,
    mce: str | None = Mce,
    version: str | None = Query(default=None, description="Preview another chart revision"),
) -> ValuesPreviewOut:
    """The chart's merged values on the cluster, layer by layer, with provenance."""
    seen = await view_of(day2, user)
    ref = seen.destination(cluster, mce).ref
    preview = await seen.guarded(day2.preview.preview(ref.id, team, addon, version=version))
    return seen.shown(ValuesPreviewOut.of(preview))


@router.post("/merge-preview")
async def merge_preview(
    body: MergePreviewBody, user: CurrentUser, day2: Services
) -> ValuesPreviewOut:
    """The merged values with edited cluster values, before writing them.

    A viewer names the cluster by its name, and a layer by its path as they read it.
    """
    seen = await view_of(day2, user)
    ref = seen.destination(body.cluster, body.mce).ref
    asked = day2.preview.preview(
        ref.id,
        body.team,
        body.addon,
        version=body.version,
        override_values=body.override_values,
        override_path=seen.repo_path(ref, body.override_path),
    )
    try:
        preview = await seen.guarded(asked)
    except ChangeRefusedError as exc:
        if seen.admin or exc.details.get("rule") != "override-path":
            raise
        raise ChangeRefusedError(
            f"{body.override_path} is not a values layer of {body.addon} on {ref.name}",
            details={"rule": "override-path", "path": body.override_path},
        ) from None
    return seen.shown(ValuesPreviewOut.of(preview))


@router.post("/clusters/{cluster}/addons/bulk", status_code=status.HTTP_201_CREATED)
async def bulk_install(
    cluster: str, body: BulkBody, user: AdminUser, day2: Services, mce: str | None = Mce
) -> BulkOut:
    """Install several charts on the cluster: one MR per team, all validated before any opens."""
    result = await day2.changes.bulk_install(
        cluster,
        [
            InstallSpec(
                team=item.team,
                chart=item.addon,
                values=item.override_values,
                version=item.version,
                emergency_pin=item.emergency_pin,
            )
            for item in body.addons
        ],
        user,
        mce=mce,
        message=body.custom_message,
    )
    return BulkOut(
        merge_requests=[ChangeOut.of_result(r) for r in result.results],
        failed=[
            BulkFailureOut(team=team, error=type(exc).__name__, detail=str(exc))
            for team, exc in result.failed
        ],
    )


@router.post("/clusters/{cluster}/addons/{team}/{addon}", status_code=status.HTTP_201_CREATED)
async def install(
    cluster: str,
    team: str,
    addon: str,
    body: InstallBody,
    user: AdminUser,
    day2: Services,
    mce: str | None = Mce,
) -> ChangeOut:
    """Open an MR installing the chart (nothing deploys until it is merged and synced)."""
    spec = InstallSpec(
        team=team,
        chart=addon,
        values=body.override_values,
        version=body.version,
        emergency_pin=body.emergency_pin,
        repourl=body.repourl,
        project_namespace=body.project_namespace,
    )
    result = await day2.changes.install(cluster, spec, user, mce=mce, message=body.message)
    return ChangeOut.of_result(result)


@router.put("/clusters/{cluster}/addons/{team}/{addon}")
async def update(
    cluster: str,
    team: str,
    addon: str,
    body: UpdateBody,
    user: AdminUser,
    day2: Services,
    mce: str | None = Mce,
) -> ChangeOut:
    """Open an MR changing the chart's values on the cluster (409 if the file moved on)."""
    result = await day2.changes.update(
        cluster,
        team,
        addon,
        body.override_values,
        user,
        version=body.version,
        emergency_pin=body.emergency_pin,
        last_commit_id=body.last_commit_id,
        mce=mce,
        message=body.message,
    )
    return ChangeOut.of_result(result)


@router.delete("/clusters/{cluster}/addons/{team}/{addon}")
async def remove(
    cluster: str,
    team: str,
    addon: str,
    user: AdminUser,
    day2: Services,
    mce: str | None = Mce,
    last_commit_id: str | None = Query(default=None),
) -> ChangeOut:
    """Open an MR deleting the chart folder. ArgoCD orphans the workload: it keeps running."""
    result = await day2.changes.remove(
        cluster, team, addon, user, last_commit_id=last_commit_id, mce=mce
    )
    return ChangeOut.of_result(result)


@router.get("/clusters/{cluster}/history")
async def history(
    cluster: str, user: CurrentUser, day2: Services, mce: str | None = Mce
) -> list[HistoryEntryOut]:
    """Commits that touched the cluster's folder, across team repos."""
    seen = await view_of(day2, user)
    ref = seen.destination(cluster, mce).ref
    commits = await seen.guarded(day2.audit.cluster_history(ref.id))
    return seen.all_shown([HistoryEntryOut.of(c.team, c.commit) for c in commits])


@router.get("/clusters/{cluster}/upgrade-check")
async def upgrade_check(
    cluster: str,
    user: CurrentUser,
    day2: Services,
    to: str = Query(description="The OCP version (or mastertag) the cluster would move to"),
    mce: str | None = Mce,
) -> UpgradeCheckOut:
    """Version-pinned charts that would silently fall back to their team default at ``to``."""
    seen = await view_of(day2, user)
    ref = seen.destination(cluster, mce).ref
    summary, found = await seen.guarded(day2.lints.upgrade_check(ref.id, to))
    return seen.shown(
        UpgradeCheckOut(
            cluster=summary.ref.id,
            from_version=summary.ocp_version,
            to_version=to.split("-", 1)[0],
            warnings=findings(found),
        )
    )
