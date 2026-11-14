"""The Events page's query (docs/notes/2026-11-13-server-scan-area-api.md §14.4).

server-scan's own parameters for ``GET /api/v1/events``, each checked before
day1 passes it on: lengths, server-scan's event-type form, a date and time
with its zone (the browser sends UTC), the page size. A filter left out is
not sent; an empty one is refused, so a blank box never filters on "".
The answers are the domain's models of server-scan's shapes, sent as they
are (``domain/server_scan_events.py``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Query
from pydantic import AwareDatetime

from wingman_day1.domain.server_scan_events import (
    CURSOR_MAX_LENGTH,
    EVENT_TYPE_MAX_LENGTH,
    EVENT_TYPE_PATTERN,
    EVENTS_PAGE_MAX,
    EVENTS_PAGE_SIZE,
    FILTER_MAX_LENGTH,
    EventQuery,
)

Filter = Annotated[str | None, Query(min_length=1, max_length=FILTER_MAX_LENGTH)]
Moment = Annotated[AwareDatetime | None, Query()]


def event_query(
    server_id: Filter = None,
    event_type: Annotated[
        str | None, Query(pattern=EVENT_TYPE_PATTERN, max_length=EVENT_TYPE_MAX_LENGTH)
    ] = None,
    actor_id: Filter = None,
    since: Moment = None,
    until: Moment = None,
    server_name: Filter = None,
    cursor: Annotated[str | None, Query(max_length=CURSOR_MAX_LENGTH)] = None,
    page_size: Annotated[int, Query(ge=1, le=EVENTS_PAGE_MAX)] = EVENTS_PAGE_SIZE,
) -> EventQuery:
    """The query's parameters as server-scan's filters; ``since`` inclusive, ``until`` exclusive."""
    return EventQuery(
        server_id=server_id,
        event_type=event_type,
        actor_id=actor_id,
        since=since,
        until=until,
        server_name=server_name,
        cursor=cursor or None,
        page_size=page_size,
    )
