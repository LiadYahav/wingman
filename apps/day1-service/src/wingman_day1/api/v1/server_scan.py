"""The Server Scan area: server-scan's pages, read through day1 (ADR-0048).

Admins only for now (decision 13 of ``docs/ideas/single-pane.md``, until
RBAC). Read only: nothing is written to server-scan. With ``SERVER_SCAN_URL``
empty every route answers 501; server-scan failing or refusing the token is
502. The contract: ``docs/notes/2026-11-13-server-scan-area-api.md``.
"""

from __future__ import annotations

from fastapi import APIRouter

from wingman_core.web.auth import AdminUser
from wingman_day1.api.deps import ServerScan
from wingman_day1.api.v1.server_scan_schemas import SitesOut

router = APIRouter(prefix="/api/day1/server-scan", tags=["server-scan"])


@router.get("/sites")
async def server_scan_sites(service: ServerScan, user: AdminUser) -> SitesOut:
    """Every configured site and the fleet, as server-scan counts them, in its shape."""
    return SitesOut.of(await service.sites())
