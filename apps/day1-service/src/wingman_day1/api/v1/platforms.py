"""The top bar's systems: segments-manager's and server-scan's own UIs (2026-11-23).

Admins only, as Quick Links (decision 13 of ``docs/ideas/single-pane.md``,
until RBAC). Built from the settings at start: nothing is called. The
amendments of ADR-0047 and ADR-0048 say why the top bar links out.
"""

from __future__ import annotations

from fastapi import APIRouter

from wingman_core.web.auth import AdminUser
from wingman_day1.api.deps import Context
from wingman_day1.api.v1.platforms_schemas import PlatformsOut

router = APIRouter(prefix="/api/day1/platforms", tags=["platforms"])


@router.get("")
async def platforms(context: Context, user: AdminUser) -> PlatformsOut:
    """Each configured system with its UI's address."""
    return PlatformsOut.of(context.platforms)
