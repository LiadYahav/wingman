"""server-scan's reads for a server's page: the record, a VM's host, History (ADR-0048, 3.25.0).

``GET /api/v1/servers/{id}`` read whole, ``/vm-host`` and ``/events``, each
answered in server-scan's own shape and read strictly into the domain's
models (``server_scan_record``, ``server_scan_events``): an answer that does
not fit is "unavailable", never a blank. The record and the VM host go with
the viewer token; History with the auditor token's header, which the
adapter passes. ``fetch`` and ``check`` are how every server-scan read goes
out and is judged; ``parsed`` and ``problem_detail`` how its answer is read.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ValidationError

from wingman_day1.domain.errors import (
    ServerNotFoundError,
    ServerScanDeniedError,
    ServerScanUnavailableError,
)
from wingman_day1.domain.server_scan_events import EventPage
from wingman_day1.domain.server_scan_record import ServerRecord, VmHostAnswer

RECORD_PATH: Final = "/api/v1/servers/{id}"
VM_HOST_PATH: Final = "/api/v1/servers/{id}/vm-host"
EVENTS_PATH: Final = "/api/v1/servers/{id}/events"
VIEWER: Final = ("token", "SERVER_SCAN_TOKEN")
AUDITOR: Final = ("auditor token", "SERVER_SCAN_AUDITOR_TOKEN")


async def fetch(
    client: httpx.AsyncClient,
    path: str,
    *,
    what: str,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, str | int] | None = None,
) -> httpx.Response:
    """``GET path``; server-scan not reached is ``ServerScanUnavailableError``."""
    try:
        return await client.get(path, headers=headers, params=params)
    except httpx.TransportError as exc:
        raise ServerScanUnavailableError(
            f"server-scan unreachable {what}: {type(exc).__name__}"
        ) from exc


def check(response: httpx.Response, *, what: str, token: tuple[str, str] = VIEWER) -> None:
    """Anything but a 200 is an error; a refused ``token`` names its setting."""
    status = response.status_code
    if status in (401, 403):
        word, setting = token
        raise ServerScanDeniedError(
            f"server-scan refused Wingman's {word} ({status}) {what}: check {setting}"
        )
    if status != 200:
        raise ServerScanUnavailableError(f"server-scan answered {status} {what}")


async def read_record(client: httpx.AsyncClient, server_id: str, *, now: datetime) -> ServerRecord:
    """The server whole, its reservation judged at ``now``; unknown: ``ServerNotFoundError``."""
    what = f"reading server {server_id}"
    response = await fetch(client, _path(RECORD_PATH, server_id), what=what)
    _found(response, f"server-scan has no server {server_id!r}")
    check(response, what=what)
    return parsed(ServerRecord, response, f"a malformed server {server_id}").judged(now)


async def read_vm_host(client: httpx.AsyncClient, server_id: str) -> VmHostAnswer:
    """A VM's host; an unknown id, or a server that is not a VM, is ``ServerNotFoundError``."""
    what = f"reading the host of {server_id}"
    response = await fetch(client, _path(VM_HOST_PATH, server_id), what=what)
    _found(response, f"server-scan has no virtual machine {server_id!r}")
    check(response, what=what)
    return parsed(VmHostAnswer, response, f"a malformed host of {server_id}")


async def read_events(
    client: httpx.AsyncClient,
    server_id: str,
    *,
    cursor: str | None,
    page_size: int,
    headers: Mapping[str, str],
) -> EventPage:
    """One page of a server's History, from ``cursor``; ``headers`` carry the auditor token."""
    what = f"reading the history of {server_id}"
    params: dict[str, str | int] = {"page_size": page_size}
    if cursor:
        params["cursor"] = cursor
    path = _path(EVENTS_PATH, server_id)
    response = await fetch(client, path, what=what, headers=headers, params=params)
    check(response, what=what, token=AUDITOR)
    return parsed(EventPage, response, f"a malformed history of {server_id}")


def _path(template: str, server_id: str) -> str:
    return template.format(id=quote(server_id, safe=""))


def _found(response: httpx.Response, fallback: str) -> None:
    """A 404 is ``ServerNotFoundError``, in server-scan's own words when it sent them."""
    if response.status_code == 404:
        raise ServerNotFoundError(problem_detail(response) or fallback)


def parsed[M: BaseModel](model: type[M], response: httpx.Response, what: str) -> M:
    """The answer read strictly into ``model``; one that does not fit is unavailable."""
    try:
        return model.model_validate_json(response.content)
    except ValidationError as exc:
        raise ServerScanUnavailableError(f"server-scan returned {what}") from exc


def problem_detail(response: httpx.Response) -> str | None:
    """server-scan's problem ``detail`` (``No server with id 'x'.``), when it sent one."""
    try:
        raw = response.json()
    except ValueError:
        return None
    detail = raw.get("detail") if isinstance(raw, dict) else None
    return f"server-scan: {detail}" if isinstance(detail, str) and detail else None
