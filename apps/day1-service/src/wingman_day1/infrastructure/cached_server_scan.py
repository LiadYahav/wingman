"""CachedServerInventory: server-scan's fleet rows and sites, cached for a few seconds per replica.

A list page that shows many clusters' nodes reads the fleet once per TTL
(ADR-0011, ADR-0038), and so does the Server Scan area's Servers page,
however many are open: the rows and the fleet are one entry (ADR-0048). The
Sites page reads server-scan's counts once per ``sites_ttl``, the Claude
page its skill once per ``skill_ttl`` (server-scan's own page reads it every
minute; the zip is never cached: it is built per download), and the
Architecture page each diagram once per ``diagram_ttl`` (they change only
when server-scan is released; about 0.7 MB each). One server is
never cached: the uninstall's check reads it fresh, so it acts on what
server-scan says now. Nor is a server's record, a VM's host or a server's
History (server-scan caches the record per revision itself, the host's
health changes without the VM changing, History comes in cursors), nor the
Confs page's catalog (a small collection server-scan reads per call, asked
for by that page only, so a cache would only delay a change). A
failure is not cached. A maintenance write clears the rows and the sites, so
the next read shows it (whatever its outcome: an ambiguous one may have
landed). The Rules & Policies page's rules and policies are read through too:
two small reads server-scan answers from its database, asked for by that page
only; and so is the Events page's audit trail (cursors and filters over a
trail that grows) and its actors (at most once a minute per open page). So
are the Jobs page's CronJobs and logs: the page polls every 5 seconds while
a Job runs, and a cached list would hide the run just started.
"""

from __future__ import annotations

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.server_scan_architecture import ArchitectureDiagram
from wingman_day1.domain.server_scan_confs import ConfList
from wingman_day1.domain.server_scan_events import EventActorList, EventPage, EventQuery
from wingman_day1.domain.server_scan_jobs import JobRun, JobsOverview, PodLogs
from wingman_day1.domain.server_scan_record import ServerRecord, VmHostAnswer
from wingman_day1.domain.server_scan_rules import ClassificationRuleList, HealthPolicyList
from wingman_day1.domain.server_scan_servers import FleetRows, MaintenanceStart, ServerMaintenance
from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.domain.server_scan_skill import Skill, SkillZip
from wingman_day1.domain.servers import ServerDetail, ServerRow
from wingman_day1.infrastructure import cache_keys as keys
from wingman_day1.ports import ServerInventory


class CachedServerInventory:
    """A ``ServerInventory`` that caches ``inner``'s fleet rows and sites."""

    def __init__(
        self,
        inner: ServerInventory,
        cache: TtlCache,
        *,
        ttl: float,
        sites_ttl: float | None = None,
        skill_ttl: float | None = None,
        diagram_ttl: float | None = None,
    ) -> None:
        """Cache ``inner``'s rows for ``ttl`` seconds; its sites, skill and diagrams as given.

        Each of ``sites_ttl``, ``skill_ttl`` and ``diagram_ttl`` defaults to ``ttl``.
        """
        self._inner = inner
        self._cache = cache
        self._ttl = ttl
        self._sites_ttl = ttl if sites_ttl is None else sites_ttl
        self._skill_ttl = ttl if skill_ttl is None else skill_ttl
        self._diagram_ttl = ttl if diagram_ttl is None else diagram_ttl

    async def rows(self) -> list[ServerRow]:
        """See ServerInventory.rows."""
        return list((await self.fleet()).rows)

    async def fleet(self) -> FleetRows:
        """See ServerInventory.fleet."""
        return await self._cache.get_or_fetch(
            keys.server_scan_rows(), self._inner.fleet, ttl=self._ttl
        )

    async def server(self, server_id: str) -> ServerDetail:
        """See ServerInventory.server; always read through."""
        return await self._inner.server(server_id)

    async def record(self, server_id: str) -> ServerRecord:
        """See ServerInventory.record; always read through."""
        return await self._inner.record(server_id)

    async def vm_host(self, server_id: str) -> VmHostAnswer:
        """See ServerInventory.vm_host; always read through."""
        return await self._inner.vm_host(server_id)

    async def server_events(
        self, server_id: str, *, cursor: str | None, page_size: int
    ) -> EventPage:
        """See ServerInventory.server_events; always read through."""
        return await self._inner.server_events(server_id, cursor=cursor, page_size=page_size)

    async def events(self, query: EventQuery) -> EventPage:
        """See ServerInventory.events; always read through."""
        return await self._inner.events(query)

    async def event_actors(self) -> EventActorList:
        """See ServerInventory.event_actors; always read through."""
        return await self._inner.event_actors()

    async def classification_rules(self) -> ClassificationRuleList:
        """See ServerInventory.classification_rules; always read through."""
        return await self._inner.classification_rules()

    async def health_policies(self) -> HealthPolicyList:
        """See ServerInventory.health_policies; always read through."""
        return await self._inner.health_policies()

    async def sites(self) -> FleetSites:
        """See ServerInventory.sites."""
        return await self._cache.get_or_fetch(
            keys.server_scan_sites(), self._inner.sites, ttl=self._sites_ttl
        )

    async def skill(self) -> Skill:
        """See ServerInventory.skill."""
        return await self._cache.get_or_fetch(
            keys.server_scan_skill(), self._inner.skill, ttl=self._skill_ttl
        )

    async def skill_zip(self, base_url: str) -> SkillZip:
        """See ServerInventory.skill_zip; always read through."""
        return await self._inner.skill_zip(base_url)

    async def architecture_diagram(self, slug: str) -> ArchitectureDiagram:
        """See ServerInventory.architecture_diagram."""
        return await self._cache.get_or_fetch(
            keys.server_scan_diagram(slug),
            lambda: self._inner.architecture_diagram(slug),
            ttl=self._diagram_ttl,
        )

    async def confs(self) -> ConfList:
        """See ServerInventory.confs; always read through."""
        return await self._inner.confs()

    async def jobs(self) -> JobsOverview:
        """See ServerInventory.jobs; always read through."""
        return await self._inner.jobs()

    async def job_logs(self, cronjob: str, job: str, pod: str, *, tail: int) -> PodLogs:
        """See ServerInventory.job_logs; always read through."""
        return await self._inner.job_logs(cronjob, job, pod, tail=tail)

    async def run_job(self, cronjob: str) -> JobRun:
        """See ServerInventory.run_job; nothing cached to clear (the Jobs are never cached)."""
        return await self._inner.run_job(cronjob)

    async def start_maintenance(self, server_id: str, start: MaintenanceStart) -> ServerMaintenance:
        """See ServerInventory.start_maintenance; clears the rows and sites."""
        try:
            return await self._inner.start_maintenance(server_id, start)
        finally:
            self._forget_fleet()

    async def end_maintenance(self, server_id: str) -> ServerMaintenance:
        """See ServerInventory.end_maintenance; clears the rows and sites."""
        try:
            return await self._inner.end_maintenance(server_id)
        finally:
            self._forget_fleet()

    def _forget_fleet(self) -> None:
        self._cache.invalidate(keys.server_scan_rows())
        self._cache.invalidate(keys.server_scan_sites())
