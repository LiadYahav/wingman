"""CachedServerInventory: server-scan's fleet rows and sites, cached for a few seconds per replica.

A list page that shows many clusters' nodes reads the fleet once per TTL
(ADR-0011, ADR-0038); the Server Scan area's Sites page reads server-scan's
counts once per ``sites_ttl`` (ADR-0048). One server is never cached: the
uninstall's check reads it fresh, so it acts on what server-scan says now. A
failure is not cached.
"""

from __future__ import annotations

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.domain.servers import ServerDetail, ServerRow
from wingman_day1.infrastructure import cache_keys as keys
from wingman_day1.ports import ServerInventory


class CachedServerInventory:
    """A ``ServerInventory`` that caches ``inner``'s fleet rows and sites."""

    def __init__(
        self, inner: ServerInventory, cache: TtlCache, *, ttl: float, sites_ttl: float | None = None
    ) -> None:
        """Cache ``inner``'s rows for ``ttl`` seconds, its sites for ``sites_ttl`` (or ``ttl``)."""
        self._inner = inner
        self._cache = cache
        self._ttl = ttl
        self._sites_ttl = ttl if sites_ttl is None else sites_ttl

    async def rows(self) -> list[ServerRow]:
        """See ServerInventory.rows."""
        return list(
            await self._cache.get_or_fetch(keys.server_scan_rows(), self._inner.rows, ttl=self._ttl)
        )

    async def server(self, server_id: str) -> ServerDetail:
        """See ServerInventory.server; always read through."""
        return await self._inner.server(server_id)

    async def sites(self) -> FleetSites:
        """See ServerInventory.sites."""
        return await self._cache.get_or_fetch(
            keys.server_scan_sites(), self._inner.sites, ttl=self._sites_ttl
        )
