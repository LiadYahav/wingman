"""server-scan's port: the one way day1 reads it, and its one write (ADR-0038, ADR-0048).

The Nodes tab, MCE placement, Inventory Management and the Server Scan area
all read server-scan through this port and its one adapter, cache and fake.
The Server Scan area's maintenance toggle is the one write (ADR-0048's 3.23.0
amendment); its server page reads a server whole, a VM's host and the
server's History (3.25.0); its Claude page reads server-scan's skill and the
skill's zip (3.27.0); its Architecture page reads the diagrams server-scan's
UI serves (3.28.0); its Confs page the hardware catalog (3.29.0); its Events
page the fleet's audit trail and who wrote it (3.31.0); its Jobs page the
CronJobs server-scan may start and a pod's log (3.32.0).
"""

from __future__ import annotations

from typing import Protocol

from wingman_day1.domain.server_scan_architecture import ArchitectureDiagram
from wingman_day1.domain.server_scan_confs import ConfList
from wingman_day1.domain.server_scan_events import EventActorList, EventPage, EventQuery
from wingman_day1.domain.server_scan_jobs import JobsOverview, PodLogs
from wingman_day1.domain.server_scan_record import ServerRecord, VmHostAnswer
from wingman_day1.domain.server_scan_rules import ClassificationRuleList, HealthPolicyList
from wingman_day1.domain.server_scan_servers import FleetRows, MaintenanceStart, ServerMaintenance
from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.domain.server_scan_skill import Skill, SkillZip
from wingman_day1.domain.servers import ServerDetail, ServerRow


class ServerInventory(Protocol):
    """server-scan: the platform's record of physical servers (ADR-0038).

    Raises ``ServerScanUnavailableError`` (``ServerScanDeniedError`` for a
    refused token) when server-scan cannot answer: servers are then unknown,
    never "none". Read only but for a server's maintenance, which the Server
    Scan area's admins turn on and off (ADR-0048).
    """

    async def rows(self) -> list[ServerRow]:
        """Every server in the fleet, as flat rows (``fleet()``'s rows)."""
        ...

    async def fleet(self) -> FleetRows:
        """The whole fleet and when it last changed: the Server Scan area's Servers page."""
        ...

    async def server(self, server_id: str) -> ServerDetail:
        """One server's name and cluster, read now (the uninstall's check).

        An unknown id is ``ServerNotFoundError``.
        """
        ...

    async def record(self, server_id: str) -> ServerRecord:
        """One server whole, read now: the Server Scan area's server page.

        An unknown id is ``ServerNotFoundError``.
        """
        ...

    async def vm_host(self, server_id: str) -> VmHostAnswer:
        """The host a KubeVirt VM runs on, resolved now; not a VM is ``ServerNotFoundError``."""
        ...

    async def server_events(
        self, server_id: str, *, cursor: str | None, page_size: int
    ) -> EventPage:
        """One page of a server's History from ``cursor``, newest first (the auditor token)."""
        ...

    async def events(self, query: EventQuery) -> EventPage:
        """One page of the audit trail ``query`` keeps, newest first (the auditor token).

        A cursor server-scan refuses is ``ServerScanRefusedError``.
        """
        ...

    async def event_actors(self) -> EventActorList:
        """Who wrote the audit trail and how much, busiest first (the auditor token)."""
        ...

    async def classification_rules(self) -> ClassificationRuleList:
        """The enabled rules that give a server its installation type (Rules & Policies)."""
        ...

    async def health_policies(self) -> HealthPolicyList:
        """The enabled policies that judge a server's health (Rules & Policies)."""
        ...

    async def sites(self) -> FleetSites:
        """server-scan's sites and fleet, as it counts them (``GET /api/v1/sites``, ADR-0048)."""
        ...

    async def skill(self) -> Skill:
        """server-scan's Claude Code skill (``GET /api/v1/skill``).

        A server-scan that carries none is ``ServerScanSkillMissingError``.
        """
        ...

    async def skill_zip(self, base_url: str) -> SkillZip:
        """The skill zipped by server-scan, ``base_url`` written in as its ``BASE_URL``."""
        ...

    async def architecture_diagram(self, slug: str) -> ArchitectureDiagram:
        """One of server-scan's architecture diagrams, as its UI serves it (no token).

        One it does not serve is ``ServerScanDiagramNotFoundError``.
        """

    async def confs(self) -> ConfList:
        """server-scan's hardware catalog, every conf it can read (``GET /api/v1/confs``)."""
        ...

    async def jobs(self) -> JobsOverview:
        """The CronJobs server-scan may start, their recent Jobs and pods (its admin token)."""
        ...

    async def job_logs(self, cronjob: str, job: str, pod: str, *, tail: int) -> PodLogs:
        """A pod's last ``tail`` lines; not of that CronJob: ``ServerScanJobNotFoundError``."""
        ...

    async def start_maintenance(self, server_id: str, start: MaintenanceStart) -> ServerMaintenance:
        """Put a server into maintenance, or update its reason. Never retried (ADR-0006).

        ``ServerNotFoundError`` for an unknown id; ``ServerScanRefusedError``
        for a body server-scan refuses; ``AmbiguousServerScanWriteError`` when
        it was sent and no answer came back.
        """
        ...

    async def end_maintenance(self, server_id: str) -> ServerMaintenance:
        """End a server's maintenance; the errors are ``start_maintenance``'s."""
        ...
