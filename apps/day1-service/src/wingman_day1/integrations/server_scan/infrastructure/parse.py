"""server-scan's server answers, read into the domain (ADR-0038).

The shapes are server-scan's ``ServerRowsResponse`` and ``ServerDetail``
(``backend/app/api/v1/schemas.py`` in team-redbull/server-scan).
A row is read for what Wingman's features use: its identity, state and
health, where it is, its maintenance, reservation and claims, its MACs. Read
strictly:
a missing required field or a value of the wrong type raises
Type/Key/ValueError, which the adapter turns into "unavailable", never into a
blank. ``server_row`` is also how the fake fleet reads its fixture, so the
fixture has server-scan's own shape.

What it follows upstream, and at which version: docs/integrations/server-scan.yaml.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from wingman_day1.domain.servers import ServerDetail, ServerRow
from wingman_day1.infrastructure.http import JSON, optional_text, required_text


def fleet_rows(raw: JSON) -> tuple[ServerRow, ...]:
    """``GET /api/v1/servers/rows``: every row, in server-scan's order."""
    if not isinstance(raw, dict):
        raise TypeError("the response is not an object")
    items = raw["items"]
    if not isinstance(items, list):
        raise TypeError("items is not a list")
    return tuple(server_row(item) for item in items)


def server_row(raw: JSON) -> ServerRow:
    """One item of ``GET /api/v1/servers/rows``; a malformed one raises Type/Key/ValueError."""
    if not isinstance(raw, dict):
        raise TypeError("a server row is not an object")
    maintenance = json_object(raw, "maintenance")
    reservation = json_object(raw, "reservation")
    held = _flag(reservation, "held", default=False)
    return ServerRow(
        id=required_text(raw, "id"),
        name=required_text(raw, "name"),
        state=required_text(raw, "openshift_state"),
        health=required_text(raw, "health"),
        serial=optional_text(raw, "serial"),
        vendor=optional_text(raw, "vendor"),
        model=optional_text(raw, "model"),
        site=optional_text(raw, "site_id"),
        cluster_name=optional_text(raw, "cluster_name"),
        mce=optional_text(raw, "mce_name"),
        maintenance=_flag(maintenance, "enabled", default=False),
        reachable=_flag(raw, "reachable"),
        stale=_flag(raw, "stale"),
        contested_with=optional_text(raw, "contested_with"),
        last_seen_at=timestamp(raw, "last_seen_at"),
        reserved_by=optional_text(reservation, "holder") if held else None,
        reserved_for_mce=optional_text(reservation, "mce_cluster") if held else None,
        reserved_for_infra_env=optional_text(reservation, "infra_env") if held else None,
        reserved_until=timestamp(reservation, "expires_at") if held else None,
        macs=_macs(raw),
    )


def server_detail(raw: JSON) -> ServerDetail:
    """``GET /api/v1/servers/{id}``: only what the uninstall's check reads."""
    if not isinstance(raw, dict):
        raise TypeError("the server is not an object")
    openshift = json_object(raw, "openshift")
    return ServerDetail(
        id=required_text(raw, "id"),
        name=required_text(raw, "name"),
        cluster_name=optional_text(openshift, "cluster_name"),
    )


def json_object(raw: Mapping[str, JSON], key: str) -> Mapping[str, JSON]:
    """``raw[key]``, an object; ``{}`` when absent or null; anything else raises TypeError."""
    value = raw.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"{key} is not an object")
    return value


def timestamp(raw: Mapping[str, JSON], key: str) -> datetime | None:
    """``raw[key]`` as an ISO 8601 instant; ``None`` when absent, null or empty."""
    value = optional_text(raw, key)
    return datetime.fromisoformat(value) if value is not None else None


def _flag(raw: Mapping[str, JSON], key: str, *, default: bool | None = None) -> bool:
    value = raw.get(key, default)
    if value is None and default is not None:
        return default
    if not isinstance(value, bool):
        raise TypeError(f"{key} is not a boolean")
    return value


def _macs(raw: Mapping[str, JSON]) -> tuple[str, ...]:
    value = raw.get("macs") or []
    if not isinstance(value, list) or not all(isinstance(mac, str) for mac in value):
        raise TypeError("macs is not a list of strings")
    return tuple(mac.lower() for mac in value)
