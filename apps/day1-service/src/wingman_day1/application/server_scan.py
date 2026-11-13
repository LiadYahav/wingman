"""The Server Scan area: server-scan's UI rebuilt in Wingman, page by page (ADR-0048).

Read through the one ``ServerInventory`` the Nodes tab, placement and
Inventory Management share (its cache in front). Each page adds its reads
here; today the Sites page. server-scan failing is
``ServerScanUnavailableError`` (``ServerScanDeniedError`` for a refused token).
"""

from __future__ import annotations

from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.ports import ServerInventory


class ServerScanService:
    """The area's use cases over server-scan."""

    def __init__(self, inventory: ServerInventory) -> None:
        """Read server-scan through ``inventory``."""
        self._inventory = inventory

    async def sites(self) -> FleetSites:
        """The Sites page: every configured site and the fleet, as server-scan counts them."""
        return await self._inventory.sites()
