"""HttpServerInventory: server-scan's fleet, one server, its sites and maintenance, over httpx.

Read only (ADR-0038, ADR-0048) but for a server's maintenance, the Server Scan
area's one write (``server_scan_writes``, ADR-0048's 3.23.0 amendment). Day1
presents a viewer token (``Authorization: Bearer``) on every read, the
auditor token on the audit trail only (a server's History, the Events page)
and the admin token on the writes only, or none for an instance that runs
with auth off.
The fleet is one read, ``GET /api/v1/servers/rows`` (about 250 KB gzipped for
3,000 servers); its weak ``ETag`` goes back as ``If-None-Match``, so an
unchanged fleet costs a 304 and no download. One server is
``GET /api/v1/servers/{id}``, read fresh for the uninstall's check. The Server
Scan area's Sites page is ``GET /api/v1/sites``, server-scan's own counts
(read by ``server_scan_sites``). A server's page reads the server whole,
a VM's host and its History (``server_scan_record``, ADR-0048's 3.25.0
amendment); the Claude page its skill and the skill's zip (``server_scan_skill``,
3.27.0). The Architecture page's diagrams come from server-scan's UI, not
its API, with no token (``server_scan_architecture``, 3.28.0). The Confs page
reads the hardware catalog (``server_scan_confs``, 3.29.0).

Any failure is ``ServerScanUnavailableError`` (``ServerScanDeniedError`` when
server-scan refuses the token): nodes are then unknown, never "none"
(ADR-0004). The answers are read by ``server_scan_parse`` (rows and one
server) and ``server_scan_sites``. The Rules & Policies page reads the enabled
classification rules and health policies (``server_scan_rules``, ADR-0048's
3.30.0 amendment); the Events page the fleet's audit trail and its actors
(``server_scan_events``, 3.31.0).
"""

from __future__ import annotations

import time
from typing import Final
from urllib.parse import quote

import httpx

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_core.ports.clock import Clock, system_clock
from wingman_day1.domain.errors import ServerNotFoundError, ServerScanUnavailableError
from wingman_day1.domain.server_scan_architecture import ArchitectureDiagram
from wingman_day1.domain.server_scan_confs import ConfList
from wingman_day1.domain.server_scan_events import EventActorList, EventPage, EventQuery
from wingman_day1.domain.server_scan_record import ServerRecord, VmHostAnswer
from wingman_day1.domain.server_scan_rules import ClassificationRuleList, HealthPolicyList
from wingman_day1.domain.server_scan_servers import FleetRows, MaintenanceStart, ServerMaintenance
from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.domain.server_scan_skill import Skill, SkillZip
from wingman_day1.domain.servers import ServerDetail, ServerRow
from wingman_day1.infrastructure.http import json_client
from wingman_day1.infrastructure.observed import Observer, ServerScanOperation, Timer
from wingman_day1.infrastructure.server_scan_architecture import read_diagram, ui_client
from wingman_day1.infrastructure.server_scan_confs import read_confs
from wingman_day1.infrastructure.server_scan_events import read_event_actors, read_fleet_events
from wingman_day1.infrastructure.server_scan_parse import fleet_rows, server_detail
from wingman_day1.infrastructure.server_scan_record import (
    check,
    fetch,
    read_events,
    read_record,
    read_vm_host,
)
from wingman_day1.infrastructure.server_scan_rules import read_policies, read_rules
from wingman_day1.infrastructure.server_scan_sites import fleet_sites
from wingman_day1.infrastructure.server_scan_skill import read_skill, read_skill_zip
from wingman_day1.infrastructure.server_scan_writes import send_maintenance, start_body

ROWS_PATH: Final = "/api/v1/servers/rows"
SERVER_PATH: Final = "/api/v1/servers/{id}"
SITES_PATH: Final = "/api/v1/sites"


class HttpServerInventory:
    """A ``ServerInventory`` over server-scan's REST API."""

    def __init__(
        self,
        *,
        base_url: str,
        ui_url: str = "",
        token: str = "",
        admin_token: str = "",
        auditor_token: str = "",
        verify: bool | str = True,
        timeout_seconds: float = 10.0,
        metrics: WingmanMetrics | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timer: Timer = time.perf_counter,
        clock: Clock = system_clock,
    ) -> None:
        """Read server-scan at ``base_url``; an empty ``token`` sends no Authorization header.

        ``ui_url`` is server-scan's UI, where its diagrams are (empty: ``base_url``).

        ``admin_token`` replaces it on the maintenance writes only, and
        ``auditor_token`` on the audit trail only (empty: those carry
        ``token``'s header, or none). ``verify`` is ``True``/``False`` or a CA
        bundle path (read now, so a missing bundle stops start-up);
        ``transport`` is for tests; ``clock`` judges a record's reservation.
        """
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._write_headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}
        self._audit_headers = {"Authorization": f"Bearer {auditor_token}"} if auditor_token else {}
        self._clock = clock
        self._observer = Observer(Dependency.SERVER_SCAN, metrics, timer=timer)
        self._client = json_client(
            base_url=base_url,
            verify=verify,
            timeout_seconds=timeout_seconds,
            transport=transport,
            headers=headers,
        )
        self._ui = ui_client(
            base_url=ui_url or base_url,
            verify=verify,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )
        self._etag: str | None = None
        self._fleet: FleetRows | None = None
        """The last fleet read, answered again (the same object) when server-scan says ``304``."""

    async def aclose(self) -> None:
        """Close the HTTP clients."""
        await self._client.aclose()
        await self._ui.aclose()

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

    async def confs(self) -> ConfList:
        """See ServerInventory.confs."""
        return await self._observer.call(ServerScanOperation.LIST_CONFS, read_confs(self._client))

    async def record(self, server_id: str) -> ServerRecord:
        """See ServerInventory.record."""
        read = read_record(self._client, server_id, now=self._clock())
        return await self._observer.call(ServerScanOperation.GET_SERVER_RECORD, read)

    async def vm_host(self, server_id: str) -> VmHostAnswer:
        """See ServerInventory.vm_host."""
        read = read_vm_host(self._client, server_id)
        return await self._observer.call(ServerScanOperation.GET_VM_HOST, read)

    async def server_events(
        self, server_id: str, *, cursor: str | None, page_size: int
    ) -> EventPage:
        """See ServerInventory.server_events."""
        read = read_events(
            self._client,
            server_id,
            cursor=cursor,
            page_size=page_size,
            headers=self._audit_headers,
        )
        return await self._observer.call(ServerScanOperation.LIST_SERVER_EVENTS, read)

    async def events(self, query: EventQuery) -> EventPage:
        """See ServerInventory.events."""
        read = read_fleet_events(self._client, query, headers=self._audit_headers)
        return await self._observer.call(ServerScanOperation.LIST_EVENTS, read)

    async def event_actors(self) -> EventActorList:
        """See ServerInventory.event_actors."""
        read = read_event_actors(self._client, headers=self._audit_headers)
        return await self._observer.call(ServerScanOperation.LIST_EVENT_ACTORS, read)

    async def skill(self) -> Skill:
        """See ServerInventory.skill."""
        return await self._observer.call(ServerScanOperation.GET_SKILL, read_skill(self._client))

    async def skill_zip(self, base_url: str) -> SkillZip:
        """See ServerInventory.skill_zip."""
        read = read_skill_zip(self._client, base_url)
        return await self._observer.call(ServerScanOperation.DOWNLOAD_SKILL, read)

    async def architecture_diagram(self, slug: str) -> ArchitectureDiagram:
        """See ServerInventory.architecture_diagram."""
        read = read_diagram(self._ui, slug)
        return await self._observer.call(ServerScanOperation.GET_ARCHITECTURE_DIAGRAM, read)

    async def classification_rules(self) -> ClassificationRuleList:
        """See ServerInventory.classification_rules."""
        read = read_rules(self._client)
        return await self._observer.call(ServerScanOperation.LIST_CLASSIFICATION_RULES, read)

    async def health_policies(self) -> HealthPolicyList:
        """See ServerInventory.health_policies."""
        read = read_policies(self._client)
        return await self._observer.call(ServerScanOperation.LIST_HEALTH_POLICIES, read)

    async def start_maintenance(self, server_id: str, start: MaintenanceStart) -> ServerMaintenance:
        """See ServerInventory.start_maintenance."""
        write = send_maintenance(
            self._client, "PUT", server_id, headers=self._write_headers, body=start_body(start)
        )
        return await self._observer.call(ServerScanOperation.ENABLE_MAINTENANCE, write)

    async def end_maintenance(self, server_id: str) -> ServerMaintenance:
        """See ServerInventory.end_maintenance."""
        write = send_maintenance(self._client, "DELETE", server_id, headers=self._write_headers)
        return await self._observer.call(ServerScanOperation.DISABLE_MAINTENANCE, write)

    async def _read_fleet(self) -> FleetRows:
        what = "listing servers"
        last = self._fleet
        headers = {"If-None-Match": self._etag} if self._etag and last is not None else {}
        response = await fetch(self._client, ROWS_PATH, what=what, headers=headers)
        if response.status_code == 304 and last is not None:
            return last
        check(response, what=what)
        try:
            fleet = fleet_rows(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise ServerScanUnavailableError("server-scan returned malformed server rows") from exc
        self._etag = response.headers.get("etag")
        self._fleet = fleet
        return fleet

    async def _server(self, server_id: str) -> ServerDetail:
        what = f"reading server {server_id}"
        path = SERVER_PATH.format(id=quote(server_id, safe=""))
        response = await fetch(self._client, path, what=what)
        if response.status_code == 404:
            raise ServerNotFoundError(f"server-scan has no server {server_id!r}")
        check(response, what=what)
        try:
            return server_detail(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise ServerScanUnavailableError(
                f"server-scan returned a malformed server {server_id}"
            ) from exc

    async def _sites(self) -> FleetSites:
        what = "listing sites"
        response = await fetch(self._client, SITES_PATH, what=what)
        check(response, what=what)
        try:
            return fleet_sites(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise ServerScanUnavailableError("server-scan returned malformed sites") from exc
