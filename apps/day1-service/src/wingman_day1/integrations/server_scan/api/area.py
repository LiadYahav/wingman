"""The Server Scan area: server-scan's pages, read through day1 (ADR-0048).

Admins only for now (decision 13 of ``docs/ideas/single-pane.md``, until
RBAC). With ``SERVER_SCAN_URL`` empty every route answers 501; server-scan
failing or refusing the token is 502. A server's page reads the record, a VM's
host and its History (the auditor token; without it, 501). The Architecture
page reads server-scan's diagrams from its UI; the Confs page, server-scan's
hardware catalog; the Events page, the fleet's audit trail and who wrote it
(the auditor token, as History). Its writes, a server's maintenance and
Fetch now, are never retried: unanswered, each is 504 ``AMBIGUOUS_WRITE``.
The contract: ``docs/notes/2026-11-13-server-scan-area-api.md``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from wingman_core.web.auth import AdminUser
from wingman_day1.api.conditional import conditional_json, weak_etag
from wingman_day1.api.deps import ServerScan
from wingman_day1.integrations.server_scan.api.architecture_schemas import DiagramOut
from wingman_day1.integrations.server_scan.api.events_schemas import event_query
from wingman_day1.integrations.server_scan.api.record_schemas import ServerRecordOut
from wingman_day1.integrations.server_scan.api.servers_schemas import (
    MaintenanceIn,
    ServerMaintenanceOut,
    ServerRowsOut,
)
from wingman_day1.integrations.server_scan.api.sites_schemas import SitesOut
from wingman_day1.integrations.server_scan.application.area import ServerScanService
from wingman_day1.integrations.server_scan.domain.architecture import DIAGRAM_SLUG
from wingman_day1.integrations.server_scan.domain.confs import ConfList
from wingman_day1.integrations.server_scan.domain.events import (
    CURSOR_MAX_LENGTH,
    EVENTS_PAGE_MAX,
    EVENTS_PAGE_SIZE,
    EventActorList,
    EventPage,
    EventQuery,
)
from wingman_day1.integrations.server_scan.domain.record import ServerRecord, VmHostAnswer
from wingman_day1.integrations.server_scan.domain.rules import (
    ClassificationRuleList,
    HealthPolicyList,
)
from wingman_day1.integrations.server_scan.domain.servers import FleetRows

router = APIRouter(prefix="/api/day1/server-scan", tags=["server-scan"])


@router.get("/sites")
async def server_scan_sites(service: ServerScan, user: AdminUser) -> SitesOut:
    """Every configured site and the fleet, as server-scan counts them, in its shape."""
    return SitesOut.of(await service.sites())


@router.get("/classification-rules")
async def server_scan_classification_rules(
    service: ServerScan, user: AdminUser
) -> ClassificationRuleList:
    """The enabled rules that give a server its installation type, in server-scan's shape."""
    return await service.classification_rules()


@router.get("/health-policies")
async def server_scan_health_policies(service: ServerScan, user: AdminUser) -> HealthPolicyList:
    """The enabled policies that judge a server's health, in server-scan's shape."""
    return await service.health_policies()


class EncodedFleet:
    """The last fleet's answer, encoded once and answered while the cache holds that fleet.

    The rows (about 2 MB for 3,000 servers) come from the one cached read of
    server-scan, the same object until it changes (ADR-0048), so polling pages
    cost neither an encode nor a hash until then.
    """

    def __init__(self) -> None:
        """Nothing encoded yet."""
        self._fleet: FleetRows | None = None
        self._details: tuple[str | None, bool, str | None] | None = None
        self._body = b""
        self._etag = ""

    def of(self, fleet: FleetRows, service: ServerScanService) -> tuple[bytes, str]:
        """``fleet``'s answer and its weak ETag."""
        details = (service.maintenance_detail, service.refresh_enabled, service.refresh_off)
        if fleet is not self._fleet or details != self._details:
            answer = ServerRowsOut.of(
                fleet,
                service.maintenance_detail,
                refresh_detail=service.refresh_off,
                refresh_enabled=service.refresh_enabled,
            )
            self._body = answer.model_dump_json().encode()
            self._etag = weak_etag(self._body)
            self._fleet, self._details = fleet, details
        return self._body, self._etag


_ENCODED = EncodedFleet()


@router.get("/servers", response_model=ServerRowsOut)
async def server_scan_servers(request: Request, service: ServerScan, user: AdminUser) -> Response:
    """The fleet as server-scan's rows; ``304`` when the ``If-None-Match`` is current."""
    body, etag = _ENCODED.of(await service.servers(), service)
    return conditional_json(request, body, etag)


@router.get("/servers/{server_id}")
async def server_scan_record(
    server_id: str, service: ServerScan, user: AdminUser
) -> ServerRecordOut:
    """A server's page: the server whole, in server-scan's shape, read now."""
    return _record(await service.record(server_id), service)


@router.get("/servers/{server_id}/vm-host")
async def server_scan_vm_host(server_id: str, service: ServerScan, user: AdminUser) -> VmHostAnswer:
    """The host a VM runs on, resolved now; 404 for a server that is not a VM."""
    return await service.vm_host(server_id)


# The fields an older server-scan does not send stay out (``domain/events.py``).
@router.get("/servers/{server_id}/events", response_model_exclude_unset=True)
async def server_scan_events(
    server_id: str,
    service: ServerScan,
    user: AdminUser,
    cursor: Annotated[str | None, Query(max_length=CURSOR_MAX_LENGTH)] = None,
    page_size: Annotated[int, Query(ge=1, le=EVENTS_PAGE_MAX)] = EVENTS_PAGE_SIZE,
) -> EventPage:
    """One page of a server's History, newest first, with server-scan's auditor token."""
    return await service.history(server_id, cursor=cursor, page_size=page_size)


# The fields an older server-scan does not send stay out (``domain/events.py``).
@router.get("/events", response_model_exclude_unset=True)
async def server_scan_fleet_events(
    service: ServerScan, user: AdminUser, query: Annotated[EventQuery, Depends(event_query)]
) -> EventPage:
    """One page of the fleet's audit trail, newest first, filtered as server-scan filters it."""
    return await service.events(query)


@router.get("/events/actors")
async def server_scan_event_actors(service: ServerScan, user: AdminUser) -> EventActorList:
    """Who wrote the audit trail and how much, busiest first: the Events page's User filter."""
    return await service.event_actors()


@router.get("/confs")
async def server_scan_confs(service: ServerScan, user: AdminUser) -> ConfList:
    """server-scan's hardware catalog in its shape: every conf it can read, and those it cannot."""
    return await service.confs()


@router.put("/servers/{server_id}/maintenance")
async def start_server_maintenance(
    server_id: str, body: MaintenanceIn, service: ServerScan, user: AdminUser
) -> ServerMaintenanceOut:
    """Put a server into maintenance, as server-scan's UI does; logged with the person's name."""
    return ServerMaintenanceOut.of(
        await service.start_maintenance(server_id, body.start(), user=user)
    )


@router.delete("/servers/{server_id}/maintenance")
async def end_server_maintenance(
    server_id: str, service: ServerScan, user: AdminUser
) -> ServerMaintenanceOut:
    """End a server's maintenance in one call, as server-scan's UI does."""
    return ServerMaintenanceOut.of(await service.end_maintenance(server_id, user=user))


@router.post("/servers/{server_id}/refresh")
async def refresh_server(server_id: str, service: ServerScan, user: AdminUser) -> ServerRecordOut:
    """Fetch now: the server read from its vendor manager now, as server-scan's button does.

    Admins only, as server-scan keeps it (its ``require_admin``); logged with the person.
    """
    return _record(await service.refresh(server_id, user=user), service)


def _record(record: ServerRecord, service: ServerScanService) -> ServerRecordOut:
    """The record with this deployment's switches: maintenance, Fetch now, History."""
    return ServerRecordOut.of(
        record,
        maintenance_detail=service.maintenance_detail,
        history_detail=service.history_detail,
        refresh_detail=service.refresh_off,
        refresh_enabled=service.refresh_enabled,
    )


@router.get("/architecture/{slug}")
async def server_scan_diagram(
    slug: Annotated[str, Path(pattern=DIAGRAM_SLUG)], service: ServerScan, user: AdminUser
) -> DiagramOut:
    """One of server-scan's architecture diagrams, the page its UI serves, for a sandboxed frame."""
    return DiagramOut.of(await service.diagram(slug))
