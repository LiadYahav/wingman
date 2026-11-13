"""The Server Scan area's Servers page: the fleet's rows and a server's maintenance (ADR-0048).

The rows are server-scan's ``GET /api/v1/servers/rows``, every field read
(``ServerRow``), with when server-scan last saw the inventory change. The one
write is a server's maintenance on and off, as server-scan's own UI does it;
server-scan takes it only from its admin token, unless it runs with auth off
(docs/notes/2026-11-13-server-scan-area-api.md §8).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from wingman_day1.domain.servers import ServerRow

MAINTENANCE_OFF: Final = (
    "Maintenance needs server-scan's admin token: add the key admin-token to the server-scan "
    "Secret and restart day1 (SERVER_SCAN_ADMIN_TOKEN)."
)
REASON_MAX_LENGTH: Final = 500
"""The longest reason day1 sends; server-scan sets no limit of its own."""


@dataclass(frozen=True, slots=True)
class FleetRows:
    """The whole fleet, as server-scan answers ``GET /api/v1/servers/rows``."""

    rows: tuple[ServerRow, ...]
    """In server-scan's order."""
    generated_at: datetime | None
    """When the inventory last changed (server-scan's newest update or sighting)."""


@dataclass(frozen=True, slots=True)
class MaintenanceStart:
    """What putting a server into maintenance sends: both optional, as server-scan's API takes."""

    reason: str | None = None
    expected_end: datetime | None = None


@dataclass(frozen=True, slots=True)
class ServerMaintenance:
    """A server's maintenance after a write, from server-scan's answer."""

    server_id: str
    server_name: str
    enabled: bool
    reason: str | None
    created_by: str | None
    """The actor server-scan records: ``api-token-admin`` for its admin token, never the person."""


def maintenance_detail(*, viewer_token: bool, admin_token: bool) -> str | None:
    """Why the maintenance toggle does not work in this deployment; ``None`` when it does.

    With the admin token the writes carry it. With no token at all server-scan
    runs with auth off (every caller is an admin there), so the writes need
    none. A viewer token alone means auth is on and the writes would be refused.
    """
    if admin_token or not viewer_token:
        return None
    return MAINTENANCE_OFF
