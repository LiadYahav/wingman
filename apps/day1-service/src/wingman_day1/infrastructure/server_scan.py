"""HttpServerInventory: server-scan's fleet, one server and its sites, over httpx.

Read only (ADR-0038, ADR-0048). Day1 presents a viewer token
(``Authorization: Bearer``), or none for an instance that runs with auth off.
The fleet is one read, ``GET /api/v1/servers/rows`` (about 250 KB gzipped for
3,000 servers); its weak ``ETag`` goes back as ``If-None-Match``, so an
unchanged fleet costs a 304 and no download. One server is
``GET /api/v1/servers/{id}``, read fresh for the uninstall's check. The Server
Scan area's Sites page is ``GET /api/v1/sites``, server-scan's own counts
(read by ``server_scan_sites``).

Any failure is ``ServerScanUnavailableError`` (``ServerScanDeniedError`` when
server-scan refuses the token): nodes are then unknown, never "none"
(ADR-0004). The answers are read by ``server_scan_parse`` (rows and one
server) and ``server_scan_sites``.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Final
from urllib.parse import quote

import httpx

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.errors import (
    ServerNotFoundError,
    ServerScanDeniedError,
    ServerScanUnavailableError,
)
from wingman_day1.domain.server_scan_servers import FleetRows
from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.domain.servers import ServerDetail, ServerRow
from wingman_day1.infrastructure.http import json_client
from wingman_day1.infrastructure.observed import Observer, ServerScanOperation, Timer
from wingman_day1.infrastructure.server_scan_parse import fleet_rows, server_detail
from wingman_day1.infrastructure.server_scan_sites import fleet_sites

ROWS_PATH: Final = "/api/v1/servers/rows"
SERVER_PATH: Final = "/api/v1/servers/{id}"
SITES_PATH: Final = "/api/v1/sites"


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
        self._client = json_client(
            base_url=base_url,
            verify=verify,
            timeout_seconds=timeout_seconds,
            transport=transport,
            headers=headers,
        )
        self._etag: str | None = None
        self._fleet: FleetRows | None = None
        """The last fleet read, answered again (the same object) when server-scan says ``304``."""

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def rows(self) -> list[ServerRow]:
        """See ServerInventory.rows."""
        return list((await self.fleet()).rows)

    async def fleet(self) -> FleetRows:
        """See ServerInventory.fleet."""
        return await self._observer.call(ServerScanOperation.LIST_SERVER_ROWS, self._read_fleet())

    async def server(self, server_id: str) -> ServerDetail:
        """See ServerInventory.server."""
        return await self._observer.call(ServerScanOperation.GET_SERVER, self._server(server_id))

    async def sites(self) -> FleetSites:
        """See ServerInventory.sites."""
        return await self._observer.call(ServerScanOperation.LIST_SITES, self._sites())

    async def _read_fleet(self) -> FleetRows:
        what = "listing servers"
        last = self._fleet
        headers = {"If-None-Match": self._etag} if self._etag and last is not None else {}
        response = await self._get(ROWS_PATH, what=what, headers=headers)
        if response.status_code == 304 and last is not None:
            return last
        _check(response, what=what)
        try:
            fleet = fleet_rows(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise ServerScanUnavailableError("server-scan returned malformed server rows") from exc
        self._etag = response.headers.get("etag")
        self._fleet = fleet
        return fleet

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

    async def _sites(self) -> FleetSites:
        what = "listing sites"
        response = await self._get(SITES_PATH, what=what)
        _check(response, what=what)
        try:
            return fleet_sites(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise ServerScanUnavailableError("server-scan returned malformed sites") from exc

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
