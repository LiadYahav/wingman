"""server-scan's port: the one way day1 reads it, and its one write (ADR-0038, ADR-0048).

The Nodes tab, MCE placement, Inventory Management and the Server Scan area
all read server-scan through this port and its one adapter, cache and fake.
The Server Scan area's maintenance toggle is the one write (ADR-0048's 3.23.0
amendment).
"""

from __future__ import annotations

from typing import Protocol

from wingman_day1.domain.server_scan_servers import FleetRows, MaintenanceStart, ServerMaintenance
from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.domain.servers import ServerDetail, ServerRow


class ServerInventory(Protocol):
    """server-scan: the platform's record of physical servers (ADR-0038).

    Raises ``ServerScanUnavailableError`` (``ServerScanDeniedError`` for a
    refused token) when server-scan cannot answer: servers are then unknown,
    never "none". Read only but for a server's maintenance, which the Server
    Scan area's admins turn on and off (ADR-0048).
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

    async def start_maintenance(self, server_id: str, start: MaintenanceStart) -> ServerMaintenance:
        """Put a server into maintenance, or update its reason. Never retried (ADR-0006).

        ``ServerNotFoundError`` for an unknown id; ``ServerScanRefusedError``
        for a body server-scan refuses; ``AmbiguousServerScanWriteError`` when
        it was sent and no answer came back.
        """
        ...

    async def end_maintenance(self, server_id: str) -> ServerMaintenance:
        """End a server's maintenance; the errors are ``start_maintenance``'s."""
        ...
