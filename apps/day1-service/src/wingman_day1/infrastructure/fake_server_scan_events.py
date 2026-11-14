"""The fake fleet's audit trail: the Events page and History with ``DAY1_FAKE_FLEET=true``.

The trail is every fake server's History (``FakeRecords.history``) and the
events of ``dev/fleet-fixtures/events.yaml``: people's, the platform's, herzi's
install lock and a pruned server's, which name their server by its fixture
name (its id and current name are filled in) or, for a server since pruned,
by an id alone. ``event_page`` filters and pages them as server-scan's
``GET /api/v1/events`` does (ADR-0048's 3.31.0 amendment): newest first,
``since`` inclusive, ``until`` exclusive, ``server_name`` a case-insensitive
part of the current name, the legacy event type, keyset cursors, the total
on the first page. A server's History is the same trail by its id, so both
pages agree. Answers are built in server-scan's JSON shape and read by the
same strict models as the real ones. Nothing here is real.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import yaml

from wingman_day1.domain.errors import ServerScanRefusedError
from wingman_day1.domain.server_scan_events import EventActorList, EventPage, EventQuery
from wingman_day1.domain.servers import ServerRow

EVENTS_FILE: Final = Path("dev/fleet-fixtures/events.yaml")
ACTORS_MAX: Final = 200
"""server-scan lists at most this many actors."""
LEGACY_EVENT_TYPES: Final = {"HEALTH_STATUS_CHANGED": "HEALTH_CHANGED"}
"""An event type server-scan renamed, matched as its new name, as there."""
_CURSOR_SEPARATOR: Final = "|"

JSONish = dict[str, Any]


def event_page(events: Iterable[JSONish], query: EventQuery) -> EventPage:
    """One page of ``events`` that ``query`` keeps, newest first, after its cursor."""
    kept = sorted((e for e in events if _matches(e, query)), key=_order, reverse=True)
    start = _after(kept, query.cursor) if query.cursor else 0
    items = kept[start : start + query.page_size]
    more = start + query.page_size < len(kept)
    answer = {
        "items": items,
        "page": {
            "next_cursor": _cursor_of(items[-1]) if more and items else None,
            "has_more": more,
            "page_size": query.page_size,
            "total": None if query.cursor else len(kept),
        },
    }
    return EventPage.model_validate_json(json.dumps(answer, default=_iso))


def event_actors(events: Iterable[JSONish]) -> EventActorList:
    """Each actor once, its type and display from its newest event, busiest first, then by id."""
    counts: Counter[str] = Counter()
    newest: dict[str, Mapping[str, Any]] = {}
    for event in sorted(events, key=_order, reverse=True):
        actor = event["actor"]
        counts[actor["id"]] += 1
        newest.setdefault(actor["id"], actor)
    ranked = sorted(counts, key=lambda actor_id: (-counts[actor_id], actor_id))[:ACTORS_MAX]
    items = [
        {
            "id": actor_id,
            "type": newest[actor_id].get("type", "SYSTEM"),
            "display": newest[actor_id].get("display"),
            "event_count": counts[actor_id],
        }
        for actor_id in ranked
    ]
    return EventActorList.model_validate_json(json.dumps({"items": items}))


def _matches(event: Mapping[str, Any], query: EventQuery) -> bool:
    """Every filter ``query`` sets keeps ``event``."""
    at: datetime = event["created_at"]
    wanted = LEGACY_EVENT_TYPES.get(query.event_type or "", query.event_type)
    checks = (
        query.server_id is None or event["server_id"] == query.server_id,
        wanted is None or event["event_type"] == wanted,
        query.actor_id is None or event["actor"]["id"] == query.actor_id,
        query.since is None or at >= query.since,
        query.until is None or at < query.until,
        _named(event, query.server_name),
    )
    return all(checks)


def _named(event: Mapping[str, Any], needle: str | None) -> bool:
    """server-scan's ``server_name``: lower case, spaces collapsed, part of the name."""
    wanted = " ".join((needle or "").lower().split())
    return not wanted or wanted in (event["server_name"] or "").lower()


def _order(event: Mapping[str, Any]) -> tuple[datetime, str]:
    return event["created_at"], event["id"]


def _cursor_of(event: Mapping[str, Any]) -> str:
    return f"{event['created_at'].isoformat()}{_CURSOR_SEPARATOR}{event['id']}"


def _after(events: Sequence[JSONish], cursor: str) -> int:
    """Where the page after ``cursor`` starts; a cursor that is not one is refused, as there."""
    at, separator, event_id = cursor.partition(_CURSOR_SEPARATOR)
    try:
        key = (datetime.fromisoformat(at), event_id)
    except ValueError:
        key = None
    if not separator or key is None or key[0].tzinfo is None:
        raise ServerScanRefusedError("server-scan: Malformed event cursor. (fake)")
    return next((i for i, event in enumerate(events) if _order(event) < key), len(events))


def _moment(value: object) -> datetime:
    """A fixture's time, quoted or as YAML reads it; one without its zone raises."""
    at = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if at.tzinfo is None:
        raise ValueError(f"an event's time needs its zone: {value!r}")
    return at


def _iso(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON")


def default_events_file() -> Path:
    """``dev/fleet-fixtures/events.yaml`` of this checkout, beside the fleet's servers."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / EVENTS_FILE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{EVENTS_FILE} not found above this file")


def load_events(path: Path, rows: Sequence[ServerRow]) -> tuple[JSONish, ...]:
    """The fixture's events in server-scan's shape; a server named that is not a row raises."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise TypeError(f"{path}: expected a mapping with an 'items' list")
    by_name = {row.name: row for row in rows}
    return tuple(_event(item, index, by_name, path) for index, item in enumerate(raw["items"]))


def _event(
    item: Mapping[str, Any], index: int, rows: Mapping[str, ServerRow], path: Path
) -> JSONish:
    server_id, server_name = item.get("server_id"), None
    if "server" in item:
        row = rows.get(item["server"])
        if row is None:
            raise ValueError(f"{path}: an event names {item['server']!r}, which is not a server")
        server_id, server_name = row.id, row.name
    return {
        "id": f"evt_fixture_{index:04d}",
        "event_type": item["event_type"],
        "server_id": server_id,
        "server_name": server_name,
        "actor": {"display": None, **item["actor"]},
        "request_id": item.get("request_id"),
        "created_at": _moment(item["created_at"]),
        "data": dict(item.get("data") or {}),
    }
