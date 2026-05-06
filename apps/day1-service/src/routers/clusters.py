"""Day1 cluster routes — provisioning and lifecycle management."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from wingman_shared.cache import CacheManager
from wingman_shared.models import (
    ClusterLiveStatus,
    ClusterMetadata,
    ClusterStatus,
    MRDetail,
)

from ..dependencies import (
    AdminUser,
    ClusterServiceDep,
    CurrentUser,
    DriftDetectorDep,
    SettingsDep,
    SpecServiceDep,
    get_cache,
    get_cluster_status_service,
)
from ..services.yaml_renderer import RenderError, apply_variable_defaults, render_spec

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/day1/clusters", tags=["clusters"])


# ── Request/response schemas ───────────────────────────────────────────────────


class CreateClusterRequest(BaseModel):
    name: str
    site: str
    mce: str
    spec_name: str
    spec_version: str
    variables: dict[str, Any]
    addon_overrides: dict[str, dict[str, Any]] | None = None


class ModifyClusterRequest(BaseModel):
    updated_yaml: str
    change_summary: str = "Cluster modification"


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("/drift-summary")
async def get_drift_summary(
    request: Request,
    cluster_svc: ClusterServiceDep,
    spec_svc: SpecServiceDep,
    drift_detector: DriftDetectorDep,
    settings: SettingsDep,
    cache: Annotated[CacheManager, Depends(get_cache)],
    user: CurrentUser,
) -> list[dict]:
    """Return drift status for all clusters — used by the cluster list and dashboard."""

    async def _compute() -> list[dict]:
        clusters = await cluster_svc.list_clusters()

        async def _check_one(cluster: ClusterStatus) -> dict:
            try:
                detail = await cluster_svc.get_cluster(
                    name=cluster.name, site=cluster.site, mce=cluster.mce
                )
                metadata = ClusterMetadata.model_validate(detail["metadata"])
                NO_SPEC = "(not linked to a cluster spec)"
                if not metadata.spec_name or metadata.spec_name == NO_SPEC:
                    return {"name": cluster.name, "is_drifted": False}

                spec = await spec_svc.get_spec(metadata.spec_name)

                installed_addons: list[dict] = []
                if spec.spec.day2.addons:
                    auth_header = request.headers.get("authorization", "")
                    try:
                        async with httpx.AsyncClient(timeout=5.0) as client:
                            resp = await client.get(
                                f"{settings.DAY2_SERVICE_URL}/api/day2/clusters/{cluster.name}/addons",
                                params={"mce": cluster.mce},
                                headers={"authorization": auth_header},
                                follow_redirects=True,
                            )
                            if resp.status_code == 200:
                                installed_addons = resp.json().get("installed", [])
                    except Exception:
                        pass

                result = await drift_detector.check_cluster(
                    cluster_name=cluster.name,
                    site=cluster.site,
                    mce=cluster.mce,
                    metadata=metadata,
                    spec=spec,
                    installed_addons=installed_addons,
                )
                return {"name": cluster.name, "is_drifted": result.is_drifted}
            except Exception as exc:
                logger.warning("Drift summary check failed for %s: %s", cluster.name, exc)
                return {"name": cluster.name, "is_drifted": False}

        results = await asyncio.gather(*[_check_one(c) for c in clusters])
        return list(results)

    return await cache.get_or_fetch("day1:drift:summary", _compute, ttl=60.0)


@router.get("", response_model=list[ClusterStatus])
async def list_clusters(
    cluster_svc: ClusterServiceDep,
    user: CurrentUser,
) -> list[ClusterStatus]:
    return await cluster_svc.list_clusters()


class BulkStatusRequest(BaseModel):
    """Request for bulk cluster status fetch."""
    clusters: list[dict[str, str]]  # [{name, mce}, ...]


@router.post("/bulk-status", response_model=dict[str, ClusterLiveStatus])
async def get_bulk_cluster_status(
    body: BulkStatusRequest,
    user: CurrentUser,
) -> dict[str, ClusterLiveStatus]:
    """
    Fetch live status for multiple clusters in parallel.

    Returns a dict mapping cluster name to its live status.
    More efficient than N individual calls when loading cluster list.
    """
    status_svc = get_cluster_status_service()
    if status_svc is None:
        raise HTTPException(
            status_code=501,
            detail="Live cluster status is not enabled. Set CLUSTER_STATUS_ENABLED=true.",
        )

    async def fetch_one(cluster: dict[str, str]) -> tuple[str, ClusterLiveStatus]:
        name = cluster["name"]
        mce = cluster["mce"]
        status = await asyncio.to_thread(status_svc.fetch_cluster_status, name, mce)
        return name, status

    # Fetch all in parallel
    results = await asyncio.gather(
        *[fetch_one(c) for c in body.clusters],
        return_exceptions=True,
    )

    statuses: dict[str, ClusterLiveStatus] = {}
    for result in results:
        if isinstance(result, BaseException):
            continue  # Skip failed fetches
        # result is tuple[str, ClusterLiveStatus]
        name, status = result
        statuses[name] = status

    return statuses


@router.get("/{name}/status", response_model=ClusterLiveStatus)
async def get_cluster_live_status(
    name: str,
    mce: Annotated[str, Query(description="MCE identifier")],
    user: CurrentUser,
) -> ClusterLiveStatus:
    """
    Fetch live HostedCluster and NodePool status from the MCE OpenShift API.

    Requires CLUSTER_STATUS_ENABLED=true. Returns 501 when the feature is disabled.
    Cannot run on minikube — only works against real OpenShift MCE clusters.
    """
    status_svc = get_cluster_status_service()
    if status_svc is None:
        raise HTTPException(
            status_code=501,
            detail="Live cluster status is not enabled. Set CLUSTER_STATUS_ENABLED=true.",
        )
    return await asyncio.to_thread(status_svc.fetch_cluster_status, name, mce)


@router.get("/{name}", response_model=dict)
async def get_cluster(
    name: str,
    site: Annotated[str, Query(description="Site identifier")],
    mce: Annotated[str, Query(description="MCE identifier")],
    cluster_svc: ClusterServiceDep,
    user: CurrentUser,
) -> dict:
    return await cluster_svc.get_cluster(name=name, site=site, mce=mce)


@router.post("", response_model=MRDetail, status_code=201)
async def create_cluster(
    body: CreateClusterRequest,
    cluster_svc: ClusterServiceDep,
    spec_svc: SpecServiceDep,
    user: AdminUser,  # viewers cannot create clusters
) -> MRDetail:
    # Load and render the spec
    spec = await spec_svc.get_spec(body.spec_name)

    if spec.metadata.version != body.spec_version:
        raise HTTPException(
            status_code=400,
            detail=f"Spec version mismatch: requested {body.spec_version}, current is {spec.metadata.version}",
        )

    variables_with_defaults = apply_variable_defaults(spec, body.variables)

    try:
        rendered_yaml = render_spec(spec, variables_with_defaults)
    except RenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return await cluster_svc.create_cluster(
        name=body.name,
        site=body.site,
        mce=body.mce,
        rendered_yaml=rendered_yaml,
        spec_name=body.spec_name,
        spec_version=body.spec_version,
        variables=variables_with_defaults,
        current_user=user,
    )


@router.patch("/{name}", response_model=MRDetail)
async def modify_cluster(
    name: str,
    body: ModifyClusterRequest,
    site: Annotated[str, Query()],
    mce: Annotated[str, Query()],
    cluster_svc: ClusterServiceDep,
    user: AdminUser,
) -> MRDetail:
    return await cluster_svc.modify_cluster(
        name=name,
        site=site,
        mce=mce,
        updated_yaml=body.updated_yaml,
        change_summary=body.change_summary,
        current_user=user,
    )


@router.delete("/{name}", response_model=MRDetail)
async def delete_cluster(
    name: str,
    site: Annotated[str, Query()],
    mce: Annotated[str, Query()],
    cluster_svc: ClusterServiceDep,
    user: AdminUser,
) -> MRDetail:
    return await cluster_svc.delete_cluster(
        name=name,
        site=site,
        mce=mce,
        current_user=user,
    )


@router.post("/{name}/sync-yaml", response_model=MRDetail)
async def sync_cluster_yaml(
    name: str,
    site: Annotated[str, Query()],
    mce: Annotated[str, Query()],
    cluster_svc: ClusterServiceDep,
    spec_svc: SpecServiceDep,
    user: AdminUser,
) -> MRDetail:
    """Re-render cluster YAML from its spec using stored variables and create an MR to apply it."""
    detail = await cluster_svc.get_cluster(name=name, site=site, mce=mce)
    metadata = ClusterMetadata.model_validate(detail["metadata"])

    if not metadata.spec_name:
        raise HTTPException(status_code=400, detail="Cluster has no associated spec")

    spec = await spec_svc.get_spec(metadata.spec_name)
    variables_with_defaults = apply_variable_defaults(spec, metadata.variables)

    try:
        rendered_yaml = render_spec(spec, variables_with_defaults)
    except RenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return await cluster_svc.modify_cluster(
        name=name,
        site=site,
        mce=mce,
        updated_yaml=rendered_yaml,
        change_summary=f"Sync cluster {name} to spec {metadata.spec_name} v{spec.metadata.version}",
        current_user=user,
    )


@router.get("/{name}/drift")
async def get_cluster_drift(
    request: Request,
    name: str,
    site: Annotated[str, Query()],
    mce: Annotated[str, Query()],
    cluster_svc: ClusterServiceDep,
    spec_svc: SpecServiceDep,
    drift_detector: DriftDetectorDep,
    settings: SettingsDep,
    user: CurrentUser,
) -> dict:
    """Check if a cluster has drifted from its spec (Day 1 YAML + Day 2 addons)."""
    # Load cluster metadata
    detail = await cluster_svc.get_cluster(name=name, site=site, mce=mce)
    metadata = ClusterMetadata.model_validate(detail["metadata"])

    NO_SPEC = "(not linked to a cluster spec)"
    if not metadata.spec_name or metadata.spec_name == NO_SPEC:
        return {"cluster": name, "is_drifted": False, "reason": "No spec associated"}

    # Load current spec
    spec = await spec_svc.get_spec(metadata.spec_name)

    # Fetch installed addons from Day 2 service (forward auth token)
    installed_addons: list[dict] = []
    if spec.spec.day2.addons:
        auth_header = request.headers.get("authorization", "")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.DAY2_SERVICE_URL}/api/day2/clusters/{name}/addons",
                    params={"mce": mce},
                    headers={"authorization": auth_header},
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    installed_addons = data.get("installed", [])
                else:
                    logger.warning(
                        "Day2 addon fetch returned %s for cluster %s — skipping addon drift",
                        resp.status_code,
                        name,
                    )
        except Exception as exc:
            logger.warning("Failed to fetch addons from Day2 for cluster %s: %s", name, exc)

    result = await drift_detector.check_cluster(
        cluster_name=name,
        site=site,
        mce=mce,
        metadata=metadata,
        spec=spec,
        installed_addons=installed_addons,
    )

    return {
        "cluster": name,
        "is_drifted": result.is_drifted,
        "spec_name": result.spec_name,
        "spec_version": result.spec_version,
        "unified_diff": result.unified_diff,
        "addon_drift": [
            {
                "addon_name": a.addon_name,
                "team": a.team,
                "reason": a.reason,
                "expected_version": a.expected_version,
                "installed_version": a.installed_version,
            }
            for a in result.addon_drift
        ],
    }
