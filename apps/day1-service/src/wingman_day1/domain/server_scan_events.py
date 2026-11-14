"""A server's History: server-scan's audit trail for it (ADR-0048's 3.25.0 amendment).

server-scan's ``GET /api/v1/servers/{id}/events`` (its ``AuditEventListResponse``
in team-redbull/server-scan at 92146d3): newest first, in keyset pages, read
only with its auditor token. An event's ``data`` is whatever its writer
recorded and is passed through as JSON; everything else is typed. Its
``event_type`` stays a string, so a type server-scan adds later still shows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from pydantic import BaseModel, JsonValue

from wingman_day1.domain.server_scan_hardware import SHAPE

EVENTS_PAGE_SIZE: Final = 50
"""server-scan's page, and its UI's."""
EVENTS_PAGE_MAX: Final = 200
"""The largest page server-scan serves."""
CURSOR_MAX_LENGTH: Final = 512
"""The longest cursor day1 passes on; server-scan's are a few dozen characters."""


class Actor(BaseModel):
    """Who did it: ``SYSTEM`` (a job), ``USER`` (a person) or ``TOKEN`` (``api-token-admin``)."""

    model_config = SHAPE

    type: str
    id: str
    display: str | None


class AuditEvent(BaseModel):
    """One event of a server's History."""

    model_config = SHAPE

    id: str
    event_type: str
    server_id: str | None
    server_name: str | None
    actor: Actor
    request_id: str | None
    created_at: datetime
    data: dict[str, JsonValue]


class EventPageInfo(BaseModel):
    """Where the next page starts; ``total`` is on the first page only."""

    model_config = SHAPE

    next_cursor: str | None
    has_more: bool
    page_size: int
    total: int | None = None


class EventPage(BaseModel):
    """One page of a server's History, newest first."""

    model_config = SHAPE

    items: tuple[AuditEvent, ...]
    page: EventPageInfo
