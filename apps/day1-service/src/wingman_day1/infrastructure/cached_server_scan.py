"""CachedServerInventory: server-scan's fleet rows and sites, cached for a few seconds per replica.

A list page that shows many clusters' nodes reads the fleet once per TTL
(ADR-0011, ADR-0038), and so does the Server Scan area's Servers page,
however many are open: the rows and the fleet are one entry (ADR-0048). The
Sites page reads server-scan's counts once per ``sites_ttl``. One server is
never cached: the uninstall's check reads it fresh, so it acts on what
server-scan says now. Nor is a server's record, a VM's host or a server's
History (server-scan caches the record per revision itself, the host's
health changes without the VM changing, History comes in cursors). A
failure is not cached. A maintenance write clears the rows and the sites, so
the next read shows it (whatever its outcome: an ambiguous one may have
landed).
"""

from __future__ import annotations

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.server_scan_events import EventPage
from wingman_day1.domain.server_scan_record import ServerRecord, VmHostAnswer
from wingman_day1.domain.server_scan_servers import FleetRows, MaintenanceStart, ServerMaintenance
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
        return list((await self.fleet()).rows)

    async def fleet(self) -> FleetRows:
        """See ServerInventory.fleet."""
        return await self._cache.get_or_fetch(
            keys.server_scan_rows(), self._inner.fleet, ttl=self._ttl
        )

    async def server(self, server_id: str) -> ServerDetail:
        """See ServerInventory.server; always read through."""
        return await self._inner.server(server_id)

    async def record(self, server_id: str) -> ServerRecord:
        """See ServerInventory.record; always read through."""
        return await self._inner.record(server_id)

    async def vm_host(self, server_id: str) -> VmHostAnswer:
        """See ServerInventory.vm_host; always read through."""
        return await self._inner.vm_host(server_id)

    async def server_events(
        self, server_id: str, *, cursor: str | None, page_size: int
    ) -> EventPage:
        """See ServerInventory.server_events; always read through."""
        return await self._inner.server_events(server_id, cursor=cursor, page_size=page_size)

    async def sites(self) -> FleetSites:
        """See ServerInventory.sites."""
        return await self._cache.get_or_fetch(
            keys.server_scan_sites(), self._inner.sites, ttl=self._sites_ttl
        )

    async def start_maintenance(self, server_id: str, start: MaintenanceStart) -> ServerMaintenance:
        """See ServerInventory.start_maintenance; clears the rows and sites."""
        try:
            return await self._inner.start_maintenance(server_id, start)
        finally:
            self._forget_fleet()

    async def end_maintenance(self, server_id: str) -> ServerMaintenance:
        """See ServerInventory.end_maintenance; clears the rows and sites."""
        try:
            return await self._inner.end_maintenance(server_id)
        finally:
            self._forget_fleet()

    def _forget_fleet(self) -> None:
        self._cache.invalidate(keys.server_scan_rows())
        self._cache.invalidate(keys.server_scan_sites())
