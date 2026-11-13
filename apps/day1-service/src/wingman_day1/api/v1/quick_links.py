"""Quick Links: the launcher page's cards (ADR-0052).

Admins only for now (decision 13 of ``docs/ideas/single-pane.md``, until RBAC).
The cards are fast: the day1 repo's tree, cached, and the links file.
"""

from __future__ import annotations

from fastapi import APIRouter

from wingman_core.web.auth import AdminUser
from wingman_day1.api.deps import QuickLinks
from wingman_day1.api.v1.quick_links_schemas import QuickLinksOut

router = APIRouter(prefix="/api/day1/quick-links", tags=["quick-links"])


@router.get("")
async def quick_links(service: QuickLinks, user: AdminUser) -> QuickLinksOut:
    """The hub's and every MCE's ArgoCD and console, by site, then the links file's sections."""
    return QuickLinksOut.of(await service.board())
