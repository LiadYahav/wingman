"""Day2 addon routes — catalog browsing and cluster addon management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from wingman_shared.models import AddonCatalogEntry, MergedAddonValues, MRDetail

from ..config import get_settings
from ..dependencies import AddonServiceDep, AdminUser, CurrentUser

router = APIRouter(prefix="/api/day2", tags=["addons"])


class GitLabInfo(BaseModel):
    """GitLab SIGs group information for external links."""
    gitlab_url: str
    sigs_group_path: str
    sigs_group_url: str


@router.get("/gitlab-info", response_model=GitLabInfo)
async def get_gitlab_info(user: CurrentUser) -> GitLabInfo:
    """Get GitLab SIGs group URL for external navigation."""
    settings = get_settings()
    return GitLabInfo(
        gitlab_url=settings.GITLAB_URL.rstrip("/"),
        sigs_group_path=settings.DAY2_SIGS_GROUP_PATH,
        sigs_group_url=f"{settings.GITLAB_URL.rstrip('/')}/groups/{settings.DAY2_SIGS_GROUP_PATH}",
    )


class InstallAddonRequest(BaseModel):
    version: str
    override_values: dict[str, Any] = {}


class BulkAddonItem(BaseModel):
    team: str
    addon: str
    version: str
    override_values: dict[str, Any] = {}


class BulkInstallRequest(BaseModel):
    addons: list[BulkAddonItem]
    custom_message: str | None = None  # Optional custom MR title/description


class MergePreviewRequest(BaseModel):
    team: str
    addon: str
    cluster: str
    mce: str
    version: str | None = None


# ── Addon catalog ──────────────────────────────────────────────────────────────


@router.get("/addons", response_model=list[AddonCatalogEntry])
async def list_addons(
    addon_svc: AddonServiceDep,
    user: CurrentUser,
    team: str | None = Query(default=None, description="Filter by team"),
) -> list[AddonCatalogEntry]:
    return await addon_svc.list_addons(team=team)


@router.get("/addons/{team}/{addon}", response_model=AddonCatalogEntry)
async def get_addon(
    team: str,
    addon: str,
    addon_svc: AddonServiceDep,
    user: CurrentUser,
) -> AddonCatalogEntry:
    entry = await addon_svc._load_catalog_entry(team, addon)
    return entry


@router.get("/addons/{team}/{addon}/versions", response_model=list[str])
async def get_addon_versions(
    team: str,
    addon: str,
    addon_svc: AddonServiceDep,
    user: CurrentUser,
) -> list[str]:
    return await addon_svc.get_addon_versions(team, addon)


@router.get("/addons/{team}/{addon}/values")
async def get_addon_values_at_version(
    team: str,
    addon: str,
    addon_svc: AddonServiceDep,
    user: CurrentUser,
    version: str = Query(..., description="Version (branch name) to fetch values for"),
) -> dict[str, Any]:
    return await addon_svc.get_addon_values_at_version(team, addon, version)


# ── Cluster addon management ───────────────────────────────────────────────────


@router.get("/clusters/{name}/history")
async def get_cluster_addon_history(
    name: str,
    addon_svc: AddonServiceDep,
    user: CurrentUser,
    mce: str = Query(...),
) -> list[dict]:
    """Return commit history for a cluster's addon override files across all team repos."""
    return await addon_svc.get_cluster_addon_history(cluster_name=name, mce=mce)


@router.get("/clusters/{name}/addons")
async def list_cluster_addons(
    name: str,
    addon_svc: AddonServiceDep,
    user: CurrentUser,
    mce: str = Query(...),
    team: str | None = Query(default=None),
) -> dict[str, Any]:
    return await addon_svc.list_cluster_addons(cluster_name=name, mce=mce, team=team)


@router.get("/clusters/{name}/addons/{team}/{addon}", response_model=MergedAddonValues)
async def get_cluster_addon(
    name: str,
    team: str,
    addon: str,
    addon_svc: AddonServiceDep,
    user: CurrentUser,
    mce: str = Query(...),
    version: str | None = Query(default=None),
) -> MergedAddonValues:
    return await addon_svc.get_merged_addon_values(
        team=team,
        addon_name=addon,
        cluster_name=name,
        mce=mce,
        version=version,
    )


@router.post("/clusters/{name}/addons/{team}/{addon}", response_model=MRDetail, status_code=201)
async def install_cluster_addon(
    name: str,
    team: str,
    addon: str,
    body: InstallAddonRequest,
    addon_svc: AddonServiceDep,
    user: AdminUser,  # viewers cannot install addons
    mce: str = Query(...),
) -> MRDetail:
    return await addon_svc.install_addon(
        team=team,
        addon_name=addon,
        cluster_name=name,
        mce=mce,
        version=body.version,
        override_values=body.override_values,
        current_user=user,
    )


@router.post("/clusters/{name}/addons/bulk", response_model=MRDetail, status_code=201)
async def bulk_install_cluster_addons(
    name: str,
    body: BulkInstallRequest,
    addon_svc: AddonServiceDep,
    user: AdminUser,
    mce: str = Query(...),
) -> MRDetail:
    """Install multiple addons on a cluster in a single MR."""
    return await addon_svc.bulk_install_addons(
        cluster_name=name,
        mce=mce,
        addons=[(a.team, a.addon, a.version, a.override_values) for a in body.addons],
        current_user=user,
        custom_message=body.custom_message,
    )


@router.put("/clusters/{name}/addons/{team}/{addon}", response_model=MRDetail)
async def update_cluster_addon(
    name: str,
    team: str,
    addon: str,
    body: InstallAddonRequest,
    addon_svc: AddonServiceDep,
    user: AdminUser,
    mce: str = Query(...),
) -> MRDetail:
    return await addon_svc.update_addon(
        team=team,
        addon_name=addon,
        cluster_name=name,
        mce=mce,
        version=body.version,
        override_values=body.override_values,
        current_user=user,
    )


@router.delete("/clusters/{name}/addons/{team}/{addon}", response_model=MRDetail)
async def remove_cluster_addon(
    name: str,
    team: str,
    addon: str,
    addon_svc: AddonServiceDep,
    user: AdminUser,
    mce: str = Query(...),
) -> MRDetail:
    return await addon_svc.remove_addon(
        team=team,
        addon_name=addon,
        cluster_name=name,
        mce=mce,
        current_user=user,
    )


# ── Merge preview ──────────────────────────────────────────────────────────────


@router.post("/merge-preview", response_model=MergedAddonValues)
async def merge_preview(
    body: MergePreviewRequest,
    addon_svc: AddonServiceDep,
    user: CurrentUser,
) -> MergedAddonValues:
    return await addon_svc.get_merged_addon_values(
        team=body.team,
        addon_name=body.addon,
        cluster_name=body.cluster,
        mce=body.mce,
        version=body.version,
    )
