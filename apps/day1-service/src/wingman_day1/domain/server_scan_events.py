"""server-scan's audit trail: a server's History and the Events page (ADR-0048, 3.25.0, 3.31.0).

server-scan's ``GET /api/v1/servers/{id}/events`` and ``GET /api/v1/events``
(its ``AuditEventListResponse`` in team-redbull/server-scan at 92146d3):
newest first, in keyset pages, read only with its auditor token; the Events
page filters the whole trail (``EventQuery``) and lists who wrote it
(``/api/v1/events/actors``). An event's ``data`` is whatever its writer
recorded and is passed through as JSON; everything else is typed. Its
``event_type`` and an actor's ``type`` stay strings, so a word server-scan
adds later still shows. Whether the audit trail can be read here is
``audit_detail``'s rule.
"""

from __future__ import annotations

from dataclasses import dataclass
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
FILTER_MAX_LENGTH: Final = 256
"""The longest server id, server name or actor id day1 passes on as a filter."""
EVENT_TYPE_PATTERN: Final = r"^[A-Z][A-Z0-9_]*$"
"""server-scan's event types (``MAINTENANCE_ENABLED``), and the legacy ones it still matches."""
EVENT_TYPE_MAX_LENGTH: Final = 64
AUDITOR_SETTING: Final = "SERVER_SCAN_AUDITOR_TOKEN"
"""Where day1 finds server-scan's auditor token."""


def audit_off(page: str) -> str:
    """The one line ``page`` of the audit trail shows when it cannot be read here."""
    return (
        f"{page} needs server-scan's auditor token: add the key auditor-token to the "
        f"server-scan Secret and restart day1 ({AUDITOR_SETTING})."
    )


HISTORY_OFF: Final = audit_off("History")
EVENTS_OFF: Final = audit_off("Events")


def audit_detail(page: str, *, viewer_token: bool, auditor_token: bool) -> str | None:
    """Why ``page`` of the audit trail does not work in this deployment; ``None`` when it does.

    As ``maintenance_detail``: with the auditor token it is read with it;
    with no token at all server-scan runs with auth off and needs none; a
    viewer token alone means auth is on, and server-scan keeps its audit
    trail from viewers.
    """
    if auditor_token or not viewer_token:
        return None
    return audit_off(page)


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


@dataclass(frozen=True, slots=True)
class EventQuery:
    """The Events page's filters and page, server-scan's ``GET /api/v1/events`` parameters.

    ``None`` leaves a filter out; they combine with AND. ``since`` is
    inclusive and ``until`` exclusive; ``server_name`` is a case-insensitive
    part of the server's name; ``cursor`` is the previous page's
    ``next_cursor`` (``None``: the first page, which carries the total).
    """

    server_id: str | None = None
    event_type: str | None = None
    actor_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    server_name: str | None = None
    cursor: str | None = None
    page_size: int = EVENTS_PAGE_SIZE


class EventActor(Actor):
    """Someone or something that wrote events, and how many (the Events page's User filter)."""

    event_count: int


class EventActorList(BaseModel):
    """Every actor of the audit trail, busiest first (at most 200, server-scan's cap)."""

    model_config = SHAPE

    items: tuple[EventActor, ...]
