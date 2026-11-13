"""The Server Scan area: server-scan's UI rebuilt in Wingman, page by page (ADR-0048).

Read through the one ``ServerInventory`` the Nodes tab, placement and
Inventory Management share (its cache in front). Each page adds its reads
here: the Sites page, and the Servers page's fleet rows. server-scan failing
is ``ServerScanUnavailableError`` (``ServerScanDeniedError`` for a refused
token).

The one write is a server's maintenance on and off (ADR-0048's 3.23.0
amendment), behind the routes' admin check. server-scan records the token as
who did it, so each write is logged here with the person's name, as node
uninstall logs its starts (``node_uninstall_started``): Wingman's record.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Mapping

from wingman_core.domain.users import User
from wingman_day1.domain.errors import AmbiguousServerScanWriteError, ServerScanWritesOffError
from wingman_day1.domain.server_scan_servers import FleetRows, MaintenanceStart, ServerMaintenance
from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.ports import ServerInventory

logger = logging.getLogger(__name__)


class ServerScanService:
    """The area's use cases over server-scan."""

    def __init__(
        self, inventory: ServerInventory, *, maintenance_detail: str | None = None
    ) -> None:
        """Read server-scan through ``inventory``.

        ``maintenance_detail`` says why the maintenance writes are off here
        (``domain.server_scan_servers.maintenance_detail``); ``None``: on.
        """
        self._inventory = inventory
        self.maintenance_detail = maintenance_detail

    async def sites(self) -> FleetSites:
        """The Sites page: every configured site and the fleet, as server-scan counts them."""
        return await self._inventory.sites()

    async def servers(self) -> FleetRows:
        """The Servers page: every server as server-scan's rows, from the shared cached read."""
        return await self._inventory.fleet()

    async def start_maintenance(
        self, server_id: str, start: MaintenanceStart, *, user: User
    ) -> ServerMaintenance:
        """Put a server into maintenance (or update its reason). Never retried (ADR-0006)."""
        self._writable()
        event = {
            "user": user.username,
            "server_id": server_id,
            "reason": start.reason or "",
            "expected_end": start.expected_end.isoformat() if start.expected_end else "",
        }
        write = self._inventory.start_maintenance(server_id, start)
        return await _recorded(write, event, done="server_maintenance_started")

    async def end_maintenance(self, server_id: str, *, user: User) -> ServerMaintenance:
        """End a server's maintenance. Never retried (ADR-0006)."""
        self._writable()
        event = {"user": user.username, "server_id": server_id}
        write = self._inventory.end_maintenance(server_id)
        return await _recorded(write, event, done="server_maintenance_ended")

    def _writable(self) -> None:
        if self.maintenance_detail is not None:
            raise ServerScanWritesOffError(self.maintenance_detail)


async def _recorded(
    write: Awaitable[ServerMaintenance], event: Mapping[str, str], *, done: str
) -> ServerMaintenance:
    """Await ``write`` and log it with the person: ``done``, or unconfirmed when unanswered."""
    try:
        result = await write
    except AmbiguousServerScanWriteError:
        logger.warning(
            "server maintenance change unconfirmed: %s",
            _fields(event),
            extra={"event": "server_maintenance_unconfirmed", "change": done, **event},
        )
        raise
    recorded = {**event, "server_name": result.server_name}
    logger.info(
        "%s: %s",
        done.replace("_", " "),
        _fields(recorded),
        extra={"event": done, **recorded},
    )
    return result


def _fields(event: Mapping[str, str]) -> str:
    return " ".join(f"{key}={value}" for key, value in event.items())
