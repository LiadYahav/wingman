"""Quick Links: the launcher page's cards, and their status dots and ArgoCD counts (ADR-0052).

Admins only for now (decision 13 of ``docs/ideas/single-pane.md``, until RBAC).
The cards are fast (the day1 repo's tree, cached, and the links file); the
status is the slow part, so it is its own route, read once the cards show.
"""

from __future__ import annotations

from fastapi import APIRouter

from wingman_core.web.auth import AdminUser
from wingman_day1.api.deps import QuickLinks
from wingman_day1.api.v1.quick_links_schemas import QuickLinksOut, QuickLinksStatusOut

router = APIRouter(prefix="/api/day1/quick-links", tags=["quick-links"])


@router.get("")
async def quick_links(service: QuickLinks, user: AdminUser) -> QuickLinksOut:
    """The hub's and every MCE's ArgoCD and console, by site, then the links file's sections."""
    return QuickLinksOut.of(await service.board())


@router.get("/status")
async def quick_links_status(service: QuickLinks, user: AdminUser) -> QuickLinksStatusOut:
    """Every link's check (up, down or unknown) and each ArgoCD's applications, counted."""
    return QuickLinksStatusOut.of(await service.status())
