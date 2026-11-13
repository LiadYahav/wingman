"""The Server Scan area's Servers page: the fleet's rows (ADR-0048).

The rows are server-scan's ``GET /api/v1/servers/rows``, every field read
(``ServerRow``), with when server-scan last saw the inventory change
(docs/notes/2026-11-13-server-scan-area-api.md §8).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from wingman_day1.domain.servers import ServerRow


@dataclass(frozen=True, slots=True)
class FleetRows:
    """The whole fleet, as server-scan answers ``GET /api/v1/servers/rows``."""

    rows: tuple[ServerRow, ...]
    """In server-scan's order."""
    generated_at: datetime | None
    """When the inventory last changed (server-scan's newest update or sighting)."""
