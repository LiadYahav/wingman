"""Site and MCE management routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from wingman_shared.models import MRDetail

from ..dependencies import AdminUser, ClusterServiceDep, CurrentUser

router = APIRouter(prefix="/api/day1/sites", tags=["sites"])


class CreateSiteRequest(BaseModel):
    name: str


class CreateMceRequest(BaseModel):
    name: str


@router.get("", response_model=list[str])
async def list_sites(
    cluster_svc: ClusterServiceDep,
    user: CurrentUser,
) -> list[str]:
    """List all available sites."""
    return await cluster_svc.list_sites()


@router.get("/{site}/mces", response_model=list[str])
async def list_mces(
    site: str,
    cluster_svc: ClusterServiceDep,
    user: CurrentUser,
) -> list[str]:
    """List all MCEs for a given site."""
    return await cluster_svc.list_mces(site)


@router.post("", response_model=MRDetail, status_code=201)
async def create_site(
    body: CreateSiteRequest,
    cluster_svc: ClusterServiceDep,
    user: AdminUser,
) -> MRDetail:
    """Create a new site (creates folder structure via MR)."""
    return await cluster_svc.create_site(body.name, user)


@router.post("/{site}/mces", response_model=MRDetail, status_code=201)
async def create_mce(
    site: str,
    body: CreateMceRequest,
    cluster_svc: ClusterServiceDep,
    user: AdminUser,
) -> MRDetail:
    """Create a new MCE within a site (creates folder structure via MR)."""
    return await cluster_svc.create_mce(site, body.name, user)
