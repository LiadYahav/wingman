"""server-scan's port: the one way day1 reads it (ADR-0038, ADR-0048).

The Nodes tab, MCE placement, Inventory Management and the Server Scan area
all read server-scan through this port and its one adapter, cache and fake.
"""

from __future__ import annotations

from typing import Protocol

from wingman_day1.domain.server_scan_servers import FleetRows
from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.domain.servers import ServerDetail, ServerRow


class ServerInventory(Protocol):
    """server-scan: the platform's record of physical servers (read only, ADR-0038).

    Raises ``ServerScanUnavailableError`` (``ServerScanDeniedError`` for a
    refused token) when server-scan cannot answer: servers are then unknown,
    never "none".
    """

    async def rows(self) -> list[ServerRow]:
        """Every server in the fleet, as flat rows (``fleet()``'s rows)."""
        ...

    async def fleet(self) -> FleetRows:
        """The whole fleet and when it last changed: the Server Scan area's Servers page."""
        ...

    async def server(self, server_id: str) -> ServerDetail:
        """One server, read now. An unknown id is ``ServerNotFoundError``."""
        ...

    async def sites(self) -> FleetSites:
        """server-scan's sites and fleet, as it counts them (``GET /api/v1/sites``, ADR-0048)."""
        ...
