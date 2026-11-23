"""server-scan's port: the one way day1 reads it (ADR-0038).

The Nodes tab, the uninstall's check, MCE placement and Inventory Management
read server-scan through this port and its one adapter, cache and fake.
Nothing is ever written to it.
"""

from __future__ import annotations

from typing import Protocol

from wingman_day1.domain.servers import ServerDetail, ServerRow


class ServerInventory(Protocol):
    """server-scan: the platform's record of physical servers (ADR-0038).

    Raises ``ServerScanUnavailableError`` (``ServerScanDeniedError`` for a
    refused token) when server-scan cannot answer: servers are then unknown,
    never "none". Read only.
    """

    async def rows(self) -> list[ServerRow]:
        """Every server in the fleet, as flat rows (``GET /api/v1/servers/rows``)."""
        ...

    async def server(self, server_id: str) -> ServerDetail:
        """One server's name and cluster, read now (the uninstall's check).

        An unknown id is ``ServerNotFoundError``.
        """
        ...
