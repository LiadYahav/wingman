"""Day1 spec routes — CRUD for cluster specs in the specs repo."""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request
from wingman_shared.cache import CacheManager
from wingman_shared.models import ClusterMetadata, ClusterSpec, MRDetail

from ..dependencies import (
    AdminUser,
    ClusterServiceDep,
    CurrentUser,
    DriftDetectorDep,
    SettingsDep,
    SpecServiceDep,
    get_cache,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/day1/specs", tags=["specs"])


@router.get("", response_model=list[ClusterSpec])
async def list_specs(
    spec_svc: SpecServiceDep,
    user: CurrentUser,
) -> list[ClusterSpec]:
    return await spec_svc.list_specs()


@router.get("/{name}", response_model=ClusterSpec)
async def get_spec(
    name: str,
    spec_svc: SpecServiceDep,
    user: CurrentUser,
) -> ClusterSpec:
    return await spec_svc.get_spec(name)


@router.post("", response_model=MRDetail, status_code=201)
async def create_spec(
    spec: ClusterSpec,
    spec_svc: SpecServiceDep,
    user: AdminUser,  # viewers cannot create specs
) -> MRDetail:
    return await spec_svc.create_spec(spec, user)


@router.put("/{name}", response_model=MRDetail)
async def update_spec(
    name: str,
    spec: ClusterSpec,
    spec_svc: SpecServiceDep,
    user: AdminUser,  # viewers cannot update specs
) -> MRDetail:
    return await spec_svc.update_spec(name, spec, user)


@router.delete("/{name}", response_model=MRDetail)
async def delete_spec(
    name: str,
    spec_svc: SpecServiceDep,
    user: AdminUser,  # viewers cannot delete specs
) -> MRDetail:
    return await spec_svc.delete_spec(name, user)


@router.get("/{name}/clusters")
async def get_spec_clusters(
    request: Request,
    name: str,
    spec_svc: SpecServiceDep,
    cluster_svc: ClusterServiceDep,
    drift_detector: DriftDetectorDep,
    settings: SettingsDep,
    cache: Annotated[CacheManager, Depends(get_cache)],
    user: CurrentUser,
) -> list[dict]:
    """List clusters created from this spec, with live drift state."""
    all_clusters = await cluster_svc.list_clusters()
    spec_clusters = [c for c in all_clusters if c.spec_name == name]

    if not spec_clusters:
        return []

    # Fast path: use the shared drift-summary cache if already populated
    cached_summary = cache.peek("day1:drift:summary")
    if cached_summary is not None:
        drift_map = {d["name"]: d["is_drifted"] for d in cached_summary}
        return [
            {
                "name": c.name,
                "site": c.site,
                "mce": c.mce,
                "phase": c.phase,
                "is_drifted": drift_map.get(c.name, False),
            }
            for c in spec_clusters
        ]

    # Slow path: cache miss — compute drift for this spec's clusters directly
    spec = await spec_svc.get_spec(name)
    auth_header = request.headers.get("authorization", "")

    async def _check_one(c) -> dict:
        try:
            detail = await cluster_svc.get_cluster(c.name, c.site, c.mce)
            metadata = ClusterMetadata.model_validate(detail["metadata"])
            installed: list[dict] = []
            if spec.spec.day2.addons:
                try:
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        resp = await client.get(
                            f"{settings.DAY2_SERVICE_URL}/api/day2/clusters/{c.name}/addons",
                            params={"mce": c.mce},
                            headers={"authorization": auth_header},
                            follow_redirects=True,
                        )
                        if resp.status_code == 200:
                            installed = resp.json().get("installed", [])
                except Exception:
                    pass
            result = await drift_detector.check_cluster(
                cluster_name=c.name,
                site=c.site,
                mce=c.mce,
                metadata=metadata,
                spec=spec,
                installed_addons=installed,
            )
            return {
                "name": c.name,
                "site": c.site,
                "mce": c.mce,
                "phase": c.phase,
                "is_drifted": result.is_drifted,
            }
        except Exception as exc:
            logger.warning("Drift check failed for %s: %s", c.name, exc)
            return {
                "name": c.name,
                "site": c.site,
                "mce": c.mce,
                "phase": c.phase,
                "is_drifted": False,
            }

    results = await asyncio.gather(*[_check_one(c) for c in spec_clusters])
    return list(results)


@router.get("/{name}/drift")
async def get_spec_drift(
    name: str,
    spec_svc: SpecServiceDep,
    cluster_svc: ClusterServiceDep,
    drift_detector: DriftDetectorDep,
    user: CurrentUser,
) -> list[dict]:
    """Check drift for all clusters created from this spec."""
    spec = await spec_svc.get_spec(name)
    all_clusters = await cluster_svc.list_clusters()
    cluster_list = [
        {"name": c.name, "site": c.site, "mce": c.mce} for c in all_clusters if c.spec_name == name
    ]

    results = await drift_detector.check_spec_clusters(
        spec_name=name,
        spec=spec,
        cluster_list=cluster_list,
    )

    return [
        {
            "cluster": r.cluster_name,
            "site": r.site,
            "mce": r.mce,
            "is_drifted": r.is_drifted,
            "spec_version": r.spec_version,
            "unified_diff": r.unified_diff,
        }
        for r in results
    ]
