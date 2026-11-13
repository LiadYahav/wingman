"""The Segments area: segments-manager's sites, statistics and segments (ADR-0047).

Admins only for now (decision 13 of ``docs/ideas/single-pane.md``, until
RBAC). Read only: nothing is written to segments-manager. With
``SEGMENTS_MANAGER_URL`` empty every route answers 501; segments-manager
failing is 502. The contract: ``docs/notes/2026-11-13-segments-area-api.md``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from wingman_core.web.auth import AdminUser
from wingman_day1.api.deps import Segments
from wingman_day1.api.v1.segments_schemas import SegmentsOut, SitesOut, StatsOut
from wingman_day1.domain.segments import SegmentQuery

router = APIRouter(prefix="/api/day1/segments", tags=["segments"])

Status = Literal["Available", "Allocated"]
SegmentType = Annotated[
    Literal["HC", "MCE", "INVENTORY", "PXE", "UPI", "HUB"] | None, Query(alias="type")
]
Site = Annotated[str | None, Query(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")]


@router.get("/sites")
async def segment_sites(service: Segments, user: AdminUser) -> SitesOut:
    """segments-manager's sites, in its order; a site may have no segments yet."""
    return SitesOut.of(await service.sites())


@router.get("/stats")
async def segment_stats(service: Segments, user: AdminUser) -> StatsOut:
    """Each site's allocated and total segments, and allocated per type."""
    return StatsOut.of(await service.stats())


@router.get("")
async def segments(
    service: Segments,
    user: AdminUser,
    site: Site = None,
    status: Status | None = None,
    type_: SegmentType = None,
    fresh: bool = False,
) -> SegmentsOut:
    """Every segment the filters match, with its holders; ``fresh`` reads its database now."""
    query = SegmentQuery(site=site, status=status, type=type_)
    return SegmentsOut.of(await service.segments(query, fresh=fresh))
