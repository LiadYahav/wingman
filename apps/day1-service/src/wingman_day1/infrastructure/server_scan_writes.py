"""server-scan's one write: a server's maintenance on and off (ADR-0048's 3.23.0 amendment).

``PUT /api/v1/servers/{id}/maintenance`` (``{reason?, expected_end?}``) and
``DELETE`` on the same path, each answering the server (``ServerDetail``),
whose ``maintenance`` is read. Sent with server-scan's admin token, or with
none to a server-scan that runs with auth off. Never retried (ADR-0006):
nothing sent is "unavailable", nothing changed; sent but unanswered (a
timeout or a connection lost after sending, a gateway's 504), or answered 200
in a shape day1 cannot read, is ``AmbiguousServerScanWriteError``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Literal
from urllib.parse import quote

import httpx

from wingman_day1.domain.errors import (
    AmbiguousServerScanWriteError,
    ServerNotFoundError,
    ServerScanDeniedError,
    ServerScanRefusedError,
    ServerScanUnavailableError,
)
from wingman_day1.domain.server_scan_servers import MaintenanceStart, ServerMaintenance
from wingman_day1.infrastructure.http import JSON, NOT_SENT, optional_text, required_text
from wingman_day1.infrastructure.server_scan_parse import json_object

MAINTENANCE_PATH: Final = "/api/v1/servers/{id}/maintenance"
CHECK_FIRST: Final = "Reload the servers and look at its row before trying again."

Method = Literal["PUT", "DELETE"]


def start_body(start: MaintenanceStart) -> dict[str, str]:
    """The ``PUT``'s body: only what was given, as server-scan's own UI sends it."""
    body: dict[str, str] = {}
    if start.reason:
        body["reason"] = start.reason
    if start.expected_end is not None:
        body["expected_end"] = start.expected_end.isoformat()
    return body


async def send_maintenance(
    client: httpx.AsyncClient,
    method: Method,
    server_id: str,
    *,
    headers: Mapping[str, str],
    body: Mapping[str, str] | None = None,
) -> ServerMaintenance:
    """Send one maintenance write and read its answer; once, whatever happens."""
    what = f"{'starting' if method == 'PUT' else 'ending'} maintenance on {server_id}"
    path = MAINTENANCE_PATH.format(id=quote(server_id, safe=""))
    try:
        response = await client.request(method, path, json=body, headers=headers)
    except NOT_SENT as exc:
        raise ServerScanUnavailableError(
            f"server-scan could not be reached {what} ({type(exc).__name__}); nothing changed"
        ) from exc
    except httpx.TransportError as exc:
        raise AmbiguousServerScanWriteError(
            f"{what} was sent to server-scan but no answer came back ({type(exc).__name__}): "
            f"it may have changed. {CHECK_FIRST}"
        ) from exc
    return _answer(response, server_id, what)


def _answer(response: httpx.Response, server_id: str, what: str) -> ServerMaintenance:
    status = response.status_code
    if status == 200:
        try:
            return server_maintenance(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise AmbiguousServerScanWriteError(
                f"server-scan accepted {what} (200) but its answer could not be read. {CHECK_FIRST}"
            ) from exc
    if status == 404:
        raise ServerNotFoundError(f"server-scan has no server {server_id!r}")
    if status in (401, 403):
        raise ServerScanDeniedError(
            f"server-scan refused Wingman's admin token ({status}) {what}: "
            "check SERVER_SCAN_ADMIN_TOKEN"
        )
    if status == 422:
        raise ServerScanRefusedError(f"server-scan refused {what}", _problem(response))
    if status == 504:
        raise AmbiguousServerScanWriteError(
            f"a gateway timed out waiting for server-scan {what}: it may have changed. "
            f"{CHECK_FIRST}"
        )
    raise ServerScanUnavailableError(f"server-scan answered {status} {what}")


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


def _problem(response: httpx.Response) -> list[str]:
    """server-scan's own words for a refusal (its problem's ``detail``), when it sent any."""
    try:
        raw = response.json()
    except ValueError:
        return []
    detail = raw.get("detail") if isinstance(raw, dict) else None
    return [detail] if isinstance(detail, str) and detail else []
