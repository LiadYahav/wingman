"""HttpServerInventory: server-scan's fleet and one server, over httpx (ADR-0038).

Read only. Day1 presents a viewer token (``Authorization: Bearer``), or none
for an instance that runs with auth off. The fleet is one read,
``GET /api/v1/servers/rows`` (about 250 KB gzipped for 3,000 servers); its
weak ``ETag`` goes back as ``If-None-Match``, so an unchanged fleet costs a
304 and no download. One server is ``GET /api/v1/servers/{id}``, read fresh
for the uninstall's check.

Any failure is ``ServerScanUnavailableError`` (``ServerScanDeniedError`` when
server-scan refuses the token): nodes are then unknown, never "none"
(ADR-0004). ``server_row`` is also how the fake fleet reads its fixture, so
the fixture has server-scan's own shape.
"""

from __future__ import annotations

import ssl
import time
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final
from urllib.parse import quote

import httpx

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.errors import (
    ServerNotFoundError,
    ServerScanDeniedError,
    ServerScanUnavailableError,
)
from wingman_day1.domain.servers import ServerDetail, ServerRow
from wingman_day1.infrastructure.observed import Observer, ServerScanOperation, Timer

JSON = Any
"""A decoded JSON value; narrowed where it is read."""

ROWS_PATH: Final = "/api/v1/servers/rows"
SERVER_PATH: Final = "/api/v1/servers/{id}"


class HttpServerInventory:
    """A ``ServerInventory`` over server-scan's REST API."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str = "",
        verify: bool | str = True,
        timeout_seconds: float = 10.0,
        metrics: WingmanMetrics | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timer: Timer = time.perf_counter,
    ) -> None:
        """Read server-scan at ``base_url``; an empty ``token`` sends no Authorization header.

        ``verify`` is ``True``/``False`` or a CA bundle path (read now, so a
        missing bundle stops start-up); ``transport`` is for tests.
        """
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._observer = Observer(Dependency.SERVER_SCAN, metrics, timer=timer)
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            verify=verify
            if isinstance(verify, bool)
            else ssl.create_default_context(cafile=verify),
            transport=transport,
            headers=headers,
        )
        self._etag: str | None = None
        self._rows: tuple[ServerRow, ...] | None = None

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def rows(self) -> list[ServerRow]:
        """See ServerInventory.rows."""
        return await self._observer.call(ServerScanOperation.LIST_SERVER_ROWS, self._fleet())

    async def server(self, server_id: str) -> ServerDetail:
        """See ServerInventory.server."""
        return await self._observer.call(ServerScanOperation.GET_SERVER, self._server(server_id))

    async def _fleet(self) -> list[ServerRow]:
        what = "listing servers"
        headers = {"If-None-Match": self._etag} if self._etag and self._rows is not None else {}
        response = await self._get(ROWS_PATH, what=what, headers=headers)
        if response.status_code == 304 and self._rows is not None:
            return list(self._rows)
        _check(response, what=what)
        try:
            rows = tuple(_rows(response.json()))
        except (ValueError, KeyError, TypeError) as exc:
            raise ServerScanUnavailableError("server-scan returned malformed server rows") from exc
        self._etag = response.headers.get("etag")
        self._rows = rows
        return list(rows)

    async def _server(self, server_id: str) -> ServerDetail:
        what = f"reading server {server_id}"
        response = await self._get(SERVER_PATH.format(id=quote(server_id, safe="")), what=what)
        if response.status_code == 404:
            raise ServerNotFoundError(f"server-scan has no server {server_id!r}")
        _check(response, what=what)
        try:
            return server_detail(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise ServerScanUnavailableError(
                f"server-scan returned a malformed server {server_id}"
            ) from exc

    async def _get(
        self, path: str, *, what: str, headers: Mapping[str, str] | None = None
    ) -> httpx.Response:
        try:
            return await self._client.get(path, headers=headers)
        except httpx.TransportError as exc:
            raise ServerScanUnavailableError(
                f"server-scan unreachable {what}: {type(exc).__name__}"
            ) from exc


def _check(response: httpx.Response, *, what: str) -> None:
    status = response.status_code
    if status in (401, 403):
        raise ServerScanDeniedError(
            f"server-scan refused Wingman's token ({status}) {what}: check SERVER_SCAN_TOKEN"
        )
    if status != 200:
        raise ServerScanUnavailableError(f"server-scan answered {status} {what}")


def _rows(raw: JSON) -> list[ServerRow]:
    if not isinstance(raw, dict):
        raise TypeError("the response is not an object")
    items = raw["items"]
    if not isinstance(items, list):
        raise TypeError("items is not a list")
    return [server_row(item) for item in items]


def server_row(raw: JSON) -> ServerRow:
    """One item of ``GET /api/v1/servers/rows``; a malformed one raises Type/Key/ValueError."""
    if not isinstance(raw, dict):
        raise TypeError("a server row is not an object")
    maintenance = _object(raw, "maintenance")
    reservation = _object(raw, "reservation")
    held = _flag(reservation, "held", default=False)
    return ServerRow(
        id=_text(raw, "id"),
        name=_text(raw, "name"),
        state=_text(raw, "openshift_state"),
        health=_text(raw, "health"),
        serial=_optional_text(raw, "serial"),
        vendor=_optional_text(raw, "vendor"),
        model=_optional_text(raw, "model"),
        site=_optional_text(raw, "site_id"),
        cluster_name=_optional_text(raw, "cluster_name"),
        mce=_optional_text(raw, "mce_name"),
        maintenance=_flag(maintenance, "enabled", default=False),
        reachable=_flag(raw, "reachable"),
        stale=_flag(raw, "stale"),
        contested=_optional_text(raw, "contested_with") is not None,
        last_seen_at=_timestamp(raw, "last_seen_at"),
        reserved_by=_optional_text(reservation, "holder") if held else None,
    )


def server_detail(raw: JSON) -> ServerDetail:
    """``GET /api/v1/servers/{id}``: only what the uninstall's check reads."""
    if not isinstance(raw, dict):
        raise TypeError("the server is not an object")
    openshift = _object(raw, "openshift")
    return ServerDetail(
        id=_text(raw, "id"),
        name=_text(raw, "name"),
        cluster_name=_optional_text(openshift, "cluster_name"),
    )


def _text(raw: Mapping[str, JSON], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is not a non-empty string")
    return value


def _optional_text(raw: Mapping[str, JSON], key: str) -> str | None:
    value = raw.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} is not a string")
    return value


def _object(raw: Mapping[str, JSON], key: str) -> Mapping[str, JSON]:
    value = raw.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"{key} is not an object")
    return value


def _flag(raw: Mapping[str, JSON], key: str, *, default: bool | None = None) -> bool:
    value = raw.get(key, default)
    if value is None and default is not None:
        return default
    if not isinstance(value, bool):
        raise TypeError(f"{key} is not a boolean")
    return value


def _timestamp(raw: Mapping[str, JSON], key: str) -> datetime | None:
    value = _optional_text(raw, key)
    return datetime.fromisoformat(value) if value is not None else None
