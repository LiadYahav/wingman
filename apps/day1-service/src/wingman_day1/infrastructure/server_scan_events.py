"""server-scan's reads for the Events page: the fleet's audit trail (ADR-0048, 3.31.0).

``GET /api/v1/events`` with the page's filters and cursor, and
``/api/v1/events/actors``, both with the auditor token's header, which the
adapter passes, as a server's History (``server_scan_record``). Each answer
is read strictly into the domain's models (``server_scan_events``): one that
does not fit is "unavailable", never a blank. A cursor server-scan refuses
(its ``400 CURSOR_INVALID``) is the caller's mistake, not server-scan failing.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC
from typing import Final

import httpx

from wingman_day1.domain.errors import ServerScanRefusedError
from wingman_day1.domain.server_scan_events import EventActorList, EventPage, EventQuery
from wingman_day1.infrastructure.server_scan_record import (
    AUDITOR,
    check,
    fetch,
    parsed,
    problem_detail,
)

EVENTS_PATH: Final = "/api/v1/events"
ACTORS_PATH: Final = "/api/v1/events/actors"


def event_params(query: EventQuery) -> dict[str, str | int]:
    """server-scan's parameters for ``query``: those given, the times in UTC."""
    params: dict[str, str | int] = {"page_size": query.page_size}
    words = {
        "server_id": query.server_id,
        "event_type": query.event_type,
        "actor_id": query.actor_id,
        "server_name": query.server_name,
        "cursor": query.cursor,
    }
    params |= {key: value for key, value in words.items() if value}
    times = {"since": query.since, "until": query.until}
    params |= {key: at.astimezone(UTC).isoformat() for key, at in times.items() if at}
    return params


async def read_fleet_events(
    client: httpx.AsyncClient, query: EventQuery, *, headers: Mapping[str, str]
) -> EventPage:
    """One page of the audit trail ``query`` keeps; ``headers`` carry the auditor token."""
    what = "listing events"
    response = await fetch(
        client, EVENTS_PATH, what=what, headers=headers, params=event_params(query)
    )
    if response.status_code == 400:
        raise ServerScanRefusedError(
            problem_detail(response) or "server-scan refused the events cursor"
        )
    check(response, what=what, token=AUDITOR)
    return parsed(EventPage, response, "malformed events")


async def read_event_actors(
    client: httpx.AsyncClient, *, headers: Mapping[str, str]
) -> EventActorList:
    """Who wrote the audit trail, busiest first; ``headers`` carry the auditor token."""
    what = "listing the events' actors"
    response = await fetch(client, ACTORS_PATH, what=what, headers=headers)
    check(response, what=what, token=AUDITOR)
    return parsed(EventActorList, response, "malformed event actors")
