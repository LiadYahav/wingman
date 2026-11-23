"""CachedServerInventory: server-scan's fleet rows, cached for a few seconds per replica.

A list page that shows many clusters' nodes reads the fleet once per TTL
(ADR-0011, ADR-0038), and so do placement and Inventory Management, however
many pages are open. One server is never cached: the uninstall's check reads
it fresh, so it acts on what server-scan says now. A failure is not cached.
"""

from __future__ import annotations

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.servers import ServerDetail, ServerRow
from wingman_day1.infrastructure import cache_keys as keys
from wingman_day1.integrations.server_scan.ports import ServerInventory


class CachedServerInventory:
    """A ``ServerInventory`` that caches ``inner``'s fleet rows."""

    def __init__(self, inner: ServerInventory, cache: TtlCache, *, ttl: float) -> None:
        """Cache ``inner``'s rows for ``ttl`` seconds."""
        self._inner = inner
        self._cache = cache
        self._ttl = ttl

    async def rows(self) -> list[ServerRow]:
        """See ServerInventory.rows."""
        return await self._cache.get_or_fetch(
            keys.server_scan_rows(), self._inner.rows, ttl=self._ttl
        )

    async def server(self, server_id: str) -> ServerDetail:
        """See ServerInventory.server; always read through."""
        return await self._inner.server(server_id)
