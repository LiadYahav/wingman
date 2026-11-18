"""server-scan's writes: a server's maintenance on and off, and Fetch now (ADR-0048).

``PUT /api/v1/servers/{id}/maintenance`` (``{reason?, expected_end?}``) and
``DELETE`` on the same path, each answering the server (``ServerDetail``),
whose ``maintenance`` is read (3.23.0 amendment). ``POST
/api/v1/servers/{id}/refresh`` (server-scan v6.5.0, no body) reads the
server from its vendor manager now and answers it whole, read as the server
page's record; server-scan waits up to its recheck timeout (four minutes for
UCS Central), so day1 waits ``REFRESH_TIMEOUT_SECONDS``, under nginx's and
the Route's 130 seconds for that path. Sent with server-scan's admin token,
or with none to a server-scan that runs with auth off.

Every write to server-scan goes out through ``send_once`` and is judged by
``accepted`` and ``refused``, so each is never retried (ADR-0006) in the same
way: nothing sent is "unavailable", nothing changed; sent but unanswered (a
timeout or a connection lost after sending, a gateway's 504), or accepted in
a shape day1 cannot read, is ``AmbiguousServerScanWriteError``, which names
what to look at (``check_first``) before trying again.

What it follows upstream, and at which version: docs/integrations/server-scan.yaml.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Final, Literal
from urllib.parse import quote

import httpx

from wingman_day1.domain.errors import (
    AmbiguousServerScanWriteError,
    ServerNotFoundError,
    ServerScanDeniedError,
    ServerScanError,
    ServerScanRefreshRefusedError,
    ServerScanRefusedError,
    ServerScanUnavailableError,
)
from wingman_day1.infrastructure.http import JSON, NOT_SENT, optional_text, required_text
from wingman_day1.integrations.server_scan.domain.record import ServerRecord
from wingman_day1.integrations.server_scan.domain.servers import MaintenanceStart, ServerMaintenance
from wingman_day1.integrations.server_scan.infrastructure.parse import json_object

MAINTENANCE_PATH: Final = "/api/v1/servers/{id}/maintenance"
REFRESH_PATH: Final = "/api/v1/servers/{id}/refresh"
CHECK_FIRST: Final = "Reload the servers and look at its row before trying again."
REFRESH_CHECK_FIRST: Final = (
    "Reload the server and look at when it was last seen before trying again."
)
REFRESH_TIMEOUT_SECONDS: Final = 120.0
"""How long day1 waits for a Fetch now: under the 130 seconds nginx and the Route give the path."""

Method = Literal["PUT", "POST", "DELETE"]


def start_body(start: MaintenanceStart) -> dict[str, str]:
    """The ``PUT``'s body: only what was given, as server-scan's own UI sends it."""
    body: dict[str, str] = {}
    if start.reason:
        body["reason"] = start.reason
    if start.expected_end is not None:
        body["expected_end"] = start.expected_end.isoformat()
    return body


async def send_once(
    client: httpx.AsyncClient,
    method: Method,
    path: str,
    *,
    what: str,
    check_first: str,
    headers: Mapping[str, str],
    body: Mapping[str, str] | None = None,
    wait_seconds: float | None = None,
) -> httpx.Response:
    """Send one write and return server-scan's answer; once, whatever happens.

    ``wait_seconds`` replaces the client's timeout for this write (none: the client's).
    """
    wait = httpx.USE_CLIENT_DEFAULT if wait_seconds is None else httpx.Timeout(wait_seconds)
    try:
        return await client.request(method, path, json=body, headers=headers, timeout=wait)
    except NOT_SENT as exc:
        raise ServerScanUnavailableError(
            f"server-scan could not be reached {what} ({type(exc).__name__}); nothing changed"
        ) from exc
    except httpx.TransportError as exc:
        raise AmbiguousServerScanWriteError(
            f"{what} was sent to server-scan but no answer came back ({type(exc).__name__}): "
            f"it may have changed. {check_first}"
        ) from exc


def accepted[T](
    response: httpx.Response, read: Callable[[httpx.Response], T], *, what: str, check_first: str
) -> T:
    """The answer to a write server-scan accepted; one day1 cannot read is ambiguous."""
    try:
        return read(response)
    except (ValueError, KeyError, TypeError) as exc:
        raise AmbiguousServerScanWriteError(
            f"server-scan accepted {what} ({response.status_code}) but its answer could not be "
            f"read. {check_first}"
        ) from exc


def refused(response: httpx.Response, *, what: str, check_first: str) -> ServerScanError:
    """The error for an answer a write has no rule of its own for, to raise."""
    status = response.status_code
    if status in (401, 403):
        return ServerScanDeniedError(
            f"server-scan refused Wingman's admin token ({status}) {what}: "
            "check SERVER_SCAN_ADMIN_TOKEN"
        )
    if status == 504:
        return AmbiguousServerScanWriteError(
            f"a gateway timed out waiting for server-scan {what}: it may have changed. "
            f"{check_first}"
        )
    return ServerScanUnavailableError(f"server-scan answered {status} {what}")


async def send_maintenance(
    client: httpx.AsyncClient,
    method: Literal["PUT", "DELETE"],
    server_id: str,
    *,
    headers: Mapping[str, str],
    body: Mapping[str, str] | None = None,
) -> ServerMaintenance:
    """Send one maintenance write and read its answer; once, whatever happens."""
    what = f"{'starting' if method == 'PUT' else 'ending'} maintenance on {server_id}"
    path = MAINTENANCE_PATH.format(id=quote(server_id, safe=""))
    response = await send_once(
        client, method, path, what=what, check_first=CHECK_FIRST, headers=headers, body=body
    )
    status = response.status_code
    if status == 200:
        return accepted(response, _maintenance_of, what=what, check_first=CHECK_FIRST)
    if status == 404:
        raise ServerNotFoundError(f"server-scan has no server {server_id!r}")
    if status == 422:
        raise ServerScanRefusedError(f"server-scan refused {what}", _problem(response))
    raise refused(response, what=what, check_first=CHECK_FIRST)


async def send_refresh(
    client: httpx.AsyncClient, server_id: str, *, headers: Mapping[str, str], now: datetime
) -> ServerRecord:
    """Fetch now: one ``POST``, never retried; the answer read as the record, judged at ``now``."""
    what = f"reading {server_id} from its vendor manager"
    path = REFRESH_PATH.format(id=quote(server_id, safe=""))
    response = await send_once(
        client,
        "POST",
        path,
        what=what,
        check_first=REFRESH_CHECK_FIRST,
        headers=headers,
        wait_seconds=REFRESH_TIMEOUT_SECONDS,
    )
    status = response.status_code
    if status == 200:
        return accepted(
            response, lambda r: _record_of(r, now), what=what, check_first=REFRESH_CHECK_FIRST
        )
    words = _problem(response)
    if status == 404:
        raise ServerNotFoundError(
            f"server-scan: {words[0]}" if words else f"no server {server_id!r}"
        )
    if status == 409:
        raise ServerScanRefreshRefusedError(
            f"server-scan: {words[0]}" if words else f"server-scan refused {what} (409)"
        )
    if status == 503:
        cause = f": {words[0]}" if words else ""
        raise ServerScanUnavailableError(
            f"server-scan could not finish {what}{cause}; nothing changed"
        )
    raise refused(response, what=what, check_first=REFRESH_CHECK_FIRST)


def server_maintenance(raw: JSON) -> ServerMaintenance:
    """The server a maintenance write answers: who it is, and its maintenance now."""
    if not isinstance(raw, dict):
        raise TypeError("the server is not an object")
    maintenance = json_object(raw, "maintenance")
    enabled = maintenance.get("enabled")
    if not isinstance(enabled, bool):
        raise TypeError("maintenance.enabled is not a boolean")
    return ServerMaintenance(
        server_id=required_text(raw, "id"),
        server_name=required_text(raw, "name"),
        enabled=enabled,
        reason=optional_text(maintenance, "reason"),
        created_by=optional_text(maintenance, "created_by"),
    )


def _maintenance_of(response: httpx.Response) -> ServerMaintenance:
    return server_maintenance(response.json())


def _record_of(response: httpx.Response, now: datetime) -> ServerRecord:
    """The server Fetch now answers, read strictly; one that does not fit raises ValueError."""
    return ServerRecord.model_validate_json(response.content).judged(now)


def _problem(response: httpx.Response) -> list[str]:
    """server-scan's own words for a refusal (its problem's ``detail``), when it sent any."""
    try:
        raw = response.json()
    except ValueError:
        return []
    detail = raw.get("detail") if isinstance(raw, dict) else None
    return [detail] if isinstance(detail, str) and detail else []
