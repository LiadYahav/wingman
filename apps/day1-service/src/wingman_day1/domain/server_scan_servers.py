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

from wingman_day1.domain.server_scan_tokens import token_detail
from wingman_day1.domain.servers import ServerRow

ADMIN_SETTING: Final = "SERVER_SCAN_ADMIN_TOKEN"
"""Where day1 finds server-scan's admin token."""
MAINTENANCE_OFF: Final = (
    "Maintenance needs server-scan's admin token: add the key admin-token to the server-scan "
    f"Secret and restart day1 ({ADMIN_SETTING})."
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
    """Why the maintenance toggle does not work in this deployment; ``None`` when it does."""
    return token_detail(MAINTENANCE_OFF, viewer_token=viewer_token, token=admin_token)
