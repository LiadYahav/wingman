"""server-scan's part of the composition root (ADR-0038, ADR-0048).

``platform_adapters`` builds the adapter (real, none, or the fake fleet's);
this puts the one cache in front of it, which the Nodes tab, placement,
Inventory Management and the Server Scan area share, and builds the area's
use case. Kept apart so ``main`` stays one screen of wiring per system.
"""

from __future__ import annotations

from typing import Final

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.application.server_scan import ServerScanService
from wingman_day1.infrastructure.cached_server_scan import CachedServerInventory
from wingman_day1.ports import ServerInventory

SITES_TTL_SECONDS: Final = 10.0
"""The longest day1 keeps server-scan's sites: server-scan caches them 30 seconds itself."""


def cached_inventory(
    inventory: ServerInventory | None, cache: TtlCache, *, ttl: float
) -> ServerInventory | None:
    """``inventory`` behind the shared cache: rows for ``ttl``, sites for at most 10 seconds."""
    if inventory is None:
        return None
    return CachedServerInventory(inventory, cache, ttl=ttl, sites_ttl=min(ttl, SITES_TTL_SECONDS))


def server_scan_service(inventory: ServerInventory | None) -> ServerScanService | None:
    """The Server Scan area over the cached ``inventory``; ``None`` without one (501)."""
    return ServerScanService(inventory) if inventory is not None else None
