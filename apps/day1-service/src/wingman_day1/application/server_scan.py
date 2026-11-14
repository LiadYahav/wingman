"""The Server Scan area: server-scan's UI rebuilt in Wingman, page by page (ADR-0048).

Read through the one ``ServerInventory`` the Nodes tab, placement and
Inventory Management share (its cache in front). Each page adds its reads
here: the Sites page, the Servers page's fleet rows, a server's page (the
record, a VM's host, History with the auditor token), the Claude page
(server-scan's skill and its zip, with server-scan's address written in, for
people: ``ui_url``), the Architecture page's diagrams from server-scan's
UI, the Confs page's hardware catalog, and the Events page's audit trail of
the fleet (the auditor token, as History); the Jobs page is its own use
case (``jobs``, ``server_scan_jobs``). server-scan failing is
``ServerScanUnavailableError`` (``ServerScanDeniedError`` for a refused
token).

The one write is a server's maintenance on and off (ADR-0048's 3.23.0
amendment), behind the routes' admin check. server-scan records the token as
who did it, so each write is logged with the person's name
(``server_scan_audit.recorded``): Wingman's record.
"""

from __future__ import annotations

from typing import Final

from wingman_core.domain.users import User
from wingman_day1.application.server_scan_audit import recorded
from wingman_day1.application.server_scan_jobs import ServerScanJobs
from wingman_day1.domain.errors import ServerScanAuditOffError, ServerScanWritesOffError
from wingman_day1.domain.server_scan_architecture import ArchitectureDiagram
from wingman_day1.domain.server_scan_confs import ConfList
from wingman_day1.domain.server_scan_events import EventActorList, EventPage, EventQuery
from wingman_day1.domain.server_scan_record import ServerRecord, VmHostAnswer
from wingman_day1.domain.server_scan_rules import ClassificationRuleList, HealthPolicyList
from wingman_day1.domain.server_scan_servers import FleetRows, MaintenanceStart, ServerMaintenance
from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.domain.server_scan_skill import AUDITOR_TOKEN_LINE, Skill, SkillZip
from wingman_day1.ports import ServerInventory

UNCONFIRMED: Final = "server_maintenance_unconfirmed"
"""The log event of a maintenance write sent and not answered."""


class ServerScanService:
    """The area's use cases over server-scan."""

    def __init__(
        self,
        inventory: ServerInventory,
        *,
        maintenance_detail: str | None = None,
        history_detail: str | None = None,
        events_detail: str | None = None,
        ui_url: str = "",
        token_line: str = AUDITOR_TOKEN_LINE,
        jobs: ServerScanJobs | None = None,
    ) -> None:
        """Read server-scan through ``inventory``.

        ``maintenance_detail`` says why the maintenance writes are off here
        (``domain.server_scan_servers.maintenance_detail``), ``history_detail``
        why a server's History is and ``events_detail`` why the Events page is
        (``domain.server_scan_events.audit_detail``); ``None``: on. ``ui_url``
        is server-scan's address for people and Claude Code; ``token_line`` the
        line its zip of the skill names (``domain.server_scan_skill.token_line``).
        ``jobs`` is the Jobs page (none: over ``inventory``, on).
        """
        self._inventory = inventory
        self.maintenance_detail = maintenance_detail
        self.history_detail = history_detail
        self.events_detail = events_detail
        self.ui_url = ui_url.rstrip("/")
        self.token_line = token_line
        self.jobs = jobs or ServerScanJobs(inventory)

    async def sites(self) -> FleetSites:
        """The Sites page: every configured site and the fleet, as server-scan counts them."""
        return await self._inventory.sites()

    async def servers(self) -> FleetRows:
        """The Servers page: every server as server-scan's rows, from the shared cached read."""
        return await self._inventory.fleet()

    async def classification_rules(self) -> ClassificationRuleList:
        """The Rules & Policies page: the enabled rules that classify a server by its fields."""
        return await self._inventory.classification_rules()

    async def health_policies(self) -> HealthPolicyList:
        """The Rules & Policies page: the enabled policies that judge a server's health."""
        return await self._inventory.health_policies()

    async def record(self, server_id: str) -> ServerRecord:
        """A server's page: the server whole, read now."""
        return await self._inventory.record(server_id)

    async def vm_host(self, server_id: str) -> VmHostAnswer:
        """The host a VM runs on, resolved now (a server's page, for a VM)."""
        return await self._inventory.vm_host(server_id)

    async def history(self, server_id: str, *, cursor: str | None, page_size: int) -> EventPage:
        """One page of a server's History, with server-scan's auditor token; off without it."""
        _audited(self.history_detail)
        return await self._inventory.server_events(server_id, cursor=cursor, page_size=page_size)

    async def events(self, query: EventQuery) -> EventPage:
        """The Events page: one page of the fleet's audit trail; off without the auditor token."""
        _audited(self.events_detail)
        return await self._inventory.events(query)

    async def event_actors(self) -> EventActorList:
        """The Events page's User filter: who wrote the audit trail, busiest first."""
        _audited(self.events_detail)
        return await self._inventory.event_actors()

    async def skill(self) -> Skill:
        """The Claude page: server-scan's Claude Code skill, as it holds it now."""
        return await self._inventory.skill()

    async def skill_zip(self) -> SkillZip:
        """The skill zipped by server-scan, with server-scan's address (``ui_url``) written in."""
        return await self._inventory.skill_zip(self.ui_url)

    async def diagram(self, slug: str) -> ArchitectureDiagram:
        """The Architecture page: one of server-scan's diagrams, as its UI serves it."""
        return await self._inventory.architecture_diagram(slug)

    async def confs(self) -> ConfList:
        """The Confs page: server-scan's hardware catalog, every conf it can read."""
        return await self._inventory.confs()

    async def start_maintenance(
        self, server_id: str, start: MaintenanceStart, *, user: User
    ) -> ServerMaintenance:
        """Put a server into maintenance (or update its reason). Never retried (ADR-0006)."""
        self._writable()
        event = {
            "user": user.username,
            "server_id": server_id,
            "reason": start.reason or "",
            "expected_end": start.expected_end.isoformat() if start.expected_end else "",
        }
        write = self._inventory.start_maintenance(server_id, start)
        return await recorded(
            write,
            event,
            done="server_maintenance_started",
            unconfirmed=UNCONFIRMED,
            answered=_named,
        )

    async def end_maintenance(self, server_id: str, *, user: User) -> ServerMaintenance:
        """End a server's maintenance. Never retried (ADR-0006)."""
        self._writable()
        event = {"user": user.username, "server_id": server_id}
        write = self._inventory.end_maintenance(server_id)
        return await recorded(
            write, event, done="server_maintenance_ended", unconfirmed=UNCONFIRMED, answered=_named
        )

    def _writable(self) -> None:
        if self.maintenance_detail is not None:
            raise ServerScanWritesOffError(self.maintenance_detail)


def _audited(detail: str | None) -> None:
    """The audit trail's guard: ``detail`` says why it cannot be read here (``None``: it can)."""
    if detail is not None:
        raise ServerScanAuditOffError(detail)


def _named(change: ServerMaintenance) -> dict[str, str]:
    """What a maintenance answer adds to its log line: the server's name."""
    return {"server_name": change.server_name}
