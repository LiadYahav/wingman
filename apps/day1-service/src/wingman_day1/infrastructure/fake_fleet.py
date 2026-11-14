"""FakeServerInventory and FakeUninstallWorkflow: server-scan and the orchestrator in memory.

Tests seed them directly; ``DAY1_FAKE_FLEET=true`` (development only) seeds
them from ``dev/fleet-fixtures/servers.yaml``, written in server-scan's own
row shape and read by the HTTP adapter's parser, and its rules and policies
(Rules & Policies) from ``rules.yaml`` (``fake_server_scan_rules``). They
raise the same domain errors as the real adapters. The fake's sites are its rows counted by
server-scan's rules over a site catalog (``fake_server_scan_sites``, ADR-0048);
its maintenance writes change the row as a server-scan with auth off does,
recording ``dev`` as who. A server's record and History are its row and its
model's hardware (``fake_server_records``, ADR-0048's 3.25.0 amendment); no
fake server is a VM unless the records fixture says so. Its Claude skill is
a folder, read and zipped as server-scan does (``fake_server_scan_skill``,
3.27.0); without one it carries none. Its architecture diagrams are
``fake_server_scan_architecture``'s (3.28.0). Its hardware catalog (the Confs
page) is the fixture's, as loaded (``fake_server_scan_confs``, 3.29.0). Its
audit trail is every server's History and the seeded ``events``, filtered and
paged as server-scan does, for the Events page and a server's History alike
(``fake_server_scan_events``, 3.31.0). Its Jobs are server-scan's fake
runner, ported (``fake_server_scan_jobs``, 3.32.0).

An uninstall walks through a few sample phases on the injected clock and then
frees the server, and its hooks remove the node from the fake MCE (which
backfills a Machine that waits for an Agent), so the local demo shows the
whole flow. The phases are a
sample for the demo, nothing more: day1 passes the real workflow's phases
through and keeps no list of them. A second start while one runs answers
like the orchestrator's 409, and a server the fake does not know fails its
run, as the real one does: refusals happen inside the run.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

import yaml

from wingman_core.ports.clock import Clock, system_clock
from wingman_day1.domain.errors import (
    ServerNotFoundError,
    ServerScanSkillMissingError,
    ServerScanUnavailableError,
    UninstallAlreadyRunningError,
    WorkflowsError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.server_scan_architecture import ArchitectureDiagram
from wingman_day1.domain.server_scan_confs import ConfList
from wingman_day1.domain.server_scan_events import EventActorList, EventPage, EventQuery
from wingman_day1.domain.server_scan_jobs import JobRun, JobsOverview, PodLogs
from wingman_day1.domain.server_scan_record import ServerRecord, VmHostAnswer, VmHostServer
from wingman_day1.domain.server_scan_rules import ClassificationRuleList, HealthPolicyList
from wingman_day1.domain.server_scan_servers import FleetRows, MaintenanceStart, ServerMaintenance
from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.domain.server_scan_skill import Skill, SkillZip
from wingman_day1.domain.servers import (
    UNINSTALL_HOLDER,
    RunSummary,
    ServerDetail,
    ServerRow,
    uninstall_workflow_id,
)
from wingman_day1.domain.workflows import WorkflowRun
from wingman_day1.infrastructure.fake_server_records import FakeRecords
from wingman_day1.infrastructure.fake_server_scan_architecture import FakeDiagrams
from wingman_day1.infrastructure.fake_server_scan_events import JSONish, event_actors, event_page
from wingman_day1.infrastructure.fake_server_scan_jobs import FakeJobs
from wingman_day1.infrastructure.fake_server_scan_rules import FakeRules
from wingman_day1.infrastructure.fake_server_scan_sites import SiteName, catalog_of, count_sites
from wingman_day1.infrastructure.fake_server_scan_skill import zip_skill
from wingman_day1.infrastructure.server_scan_parse import server_row

DEMO_PHASES: Final = (
    "checking-inventory",
    "draining-node",
    "awaiting-machine-deletion",
    "removing-from-inventory",
)
"""A few of the real workflow's steps, for the demo only."""
PHASE_SECONDS: Final = 8.0
FAKE_ACTOR: Final = "dev"
"""Who a server-scan with auth off records for every write."""
FLEET_FILE: Final = Path("dev/fleet-fixtures/servers.yaml")


class FakeServerInventory:
    """A ``ServerInventory`` over seeded rows; ``unavailable`` fails every call, as if down."""

    def __init__(
        self,
        rows: Iterable[ServerRow] = (),
        *,
        unavailable: bool = False,
        rules: FakeRules | None = None,
        sites: Sequence[SiteName] = (),
        records: FakeRecords | None = None,
        skill: Skill | None = None,
        diagrams: FakeDiagrams | None = None,
        confs: ConfList | None = None,
        events: Sequence[JSONish] = (),
        jobs: FakeJobs | None = None,
        clock: Clock = system_clock,
    ) -> None:
        """Seed the fleet; ``sites`` is server-scan's site catalog (none: the rows' own sites).

        ``records`` gives each model its hardware (none: every record has none);
        ``skill`` is the Claude skill it serves (none: it carries none).
        ``diagrams`` are the UI's architecture diagrams (none: it serves none).
        ``confs`` is the hardware catalog (none: empty).
        ``rules`` are its classification rules and health policies (none: none).
        ``events`` join the servers' History in its audit trail (``load_events``).
        ``jobs`` are its CronJobs (none: none, the feature on).
        """
        self._rows = {row.id: row for row in rows}
        self.unavailable = unavailable
        self._rules = rules or FakeRules()
        self._sites = tuple(sites)
        self._records = records or FakeRecords()
        self._skill = skill
        self._diagrams = diagrams or FakeDiagrams()
        self._confs = confs or ConfList(items=())
        self._events = tuple(events)
        self._jobs = jobs or FakeJobs(clock=clock)
        self._clock = clock
        self.server_reads = 0
        """How many times ``server`` was called (the uninstall's fresh read)."""
        self.maintenance_starts: list[tuple[str, MaintenanceStart]] = []
        """Every ``start_maintenance`` that reached a server, in order."""
        self.job_starts: list[str] = []
        """Every ``run_job`` that reached the fake server-scan, in order."""
        self._before_read: list[Callable[[], None]] = []

    def before_read(self, hook: Callable[[], None]) -> None:
        """Run ``hook`` before every read: the fake workflow moves its runs on."""
        self._before_read.append(hook)

    def by_id(self, server_id: str) -> ServerRow | None:
        """The server with this id."""
        return self._rows.get(server_id)

    def by_name(self, name: str) -> ServerRow | None:
        """The server with this name, ignoring case."""
        return next((r for r in self._rows.values() if r.name.lower() == name.lower()), None)

    def replace(self, row: ServerRow) -> None:
        """Put ``row`` in place of the server with its id."""
        self._rows[row.id] = row

    def snapshot(self) -> list[ServerRow]:
        """Every server now, by name, without running the read hooks (a fake workflow's look)."""
        return sorted(self._rows.values(), key=lambda row: row.name)

    async def rows(self) -> list[ServerRow]:
        """See ServerInventory.rows."""
        return list((await self.fleet()).rows)

    async def fleet(self) -> FleetRows:
        """See ServerInventory.fleet: by name; changed when the newest row was last seen."""
        self._read()
        rows = tuple(sorted(self._rows.values(), key=lambda row: row.name))
        seen = [row.last_seen_at for row in rows if row.last_seen_at is not None]
        return FleetRows(rows=rows, generated_at=max(seen, default=None))

    async def server(self, server_id: str) -> ServerDetail:
        """See ServerInventory.server."""
        self._read()
        self.server_reads += 1
        row = self._rows.get(server_id)
        if row is None:
            raise ServerNotFoundError(f"server-scan has no server {server_id!r} (fake)")
        return ServerDetail(id=row.id, name=row.name, cluster_name=row.cluster_name)

    async def record(self, server_id: str) -> ServerRecord:
        """See ServerInventory.record."""
        return self._records.record(self._writable(server_id), self._clock())

    async def vm_host(self, server_id: str) -> VmHostAnswer:
        """See ServerInventory.vm_host: the host found by its node's name (as a fallback there)."""
        record = await self.record(server_id)
        vm = record.vm_host
        if vm is None:
            raise ServerNotFoundError(
                f"server-scan: Server {record.name!r} is not a virtual machine."
            )
        host = self.by_name(vm.node_name) if vm.node_name else None
        match = "NOT_RUNNING" if vm.node_name is None else "NAME" if host else "NOT_IN_INVENTORY"
        summary = self._host(host) if host else None
        return VmHostAnswer(
            cluster_name=vm.cluster_name, node_name=vm.node_name, match=match, host=summary
        )

    async def server_events(
        self, server_id: str, *, cursor: str | None, page_size: int
    ) -> EventPage:
        """See ServerInventory.server_events: the trail by its id (unknown: empty, as there)."""
        query = EventQuery(server_id=server_id, cursor=cursor, page_size=page_size)
        return event_page(self._trail(), query)

    async def events(self, query: EventQuery) -> EventPage:
        """See ServerInventory.events."""
        return event_page(self._trail(), query)

    async def event_actors(self) -> EventActorList:
        """See ServerInventory.event_actors."""
        return event_actors(self._trail())

    async def classification_rules(self) -> ClassificationRuleList:
        """See ServerInventory.classification_rules: the seeded ones, as server-scan seeds them."""
        self._read()
        return self._rules.rules

    async def health_policies(self) -> HealthPolicyList:
        """See ServerInventory.health_policies: the seeded ones."""
        self._read()
        return self._rules.policies

    async def sites(self) -> FleetSites:
        """See ServerInventory.sites: the rows now, counted as server-scan counts them."""
        self._read()
        rows = list(self._rows.values())
        return count_sites(rows, self._sites or catalog_of(rows))

    async def skill(self) -> Skill:
        """See ServerInventory.skill."""
        return self._carried_skill()

    async def skill_zip(self, base_url: str) -> SkillZip:
        """See ServerInventory.skill_zip: zipped as server-scan zips it, for an admin."""
        return zip_skill(self._carried_skill(), base_url)

    async def architecture_diagram(self, slug: str) -> ArchitectureDiagram:
        """See ServerInventory.architecture_diagram."""
        self._read()
        return self._diagrams.diagram(slug)

    async def confs(self) -> ConfList:
        """See ServerInventory.confs: the seeded catalog, as server-scan's fake seeds it once."""
        self._read()
        return self._confs

    async def jobs(self) -> JobsOverview:
        """See ServerInventory.jobs: the fake runner's, each run judged on its clock."""
        self._read()
        return self._jobs.overview()

    async def job_logs(self, cronjob: str, job: str, pod: str, *, tail: int) -> PodLogs:
        """See ServerInventory.job_logs."""
        self._read()
        return self._jobs.logs(cronjob, job, pod, tail=tail)

    async def run_job(self, cronjob: str) -> JobRun:
        """See ServerInventory.run_job: by ``dev``, as a server-scan with auth off records it."""
        self._read()
        self.job_starts.append(cronjob)
        return self._jobs.run(cronjob, triggered_by=FAKE_ACTOR)

    async def start_maintenance(self, server_id: str, start: MaintenanceStart) -> ServerMaintenance:
        """See ServerInventory.start_maintenance: who stays the first one's, as in server-scan."""
        row = self._writable(server_id)
        self.maintenance_starts.append((server_id, start))
        who = row.maintenance_by if row.maintenance else FAKE_ACTOR
        changed = dataclasses.replace(
            row, maintenance=True, maintenance_reason=start.reason, maintenance_by=who
        )
        self._records.log_maintenance(
            row, changed, at=self._clock(), expected_end=start.expected_end
        )
        return self._change(changed)

    async def end_maintenance(self, server_id: str) -> ServerMaintenance:
        """See ServerInventory.end_maintenance."""
        row = self._writable(server_id)
        changed = dataclasses.replace(
            row, maintenance=False, maintenance_reason=None, maintenance_by=None
        )
        self._records.log_maintenance(row, changed, at=self._clock())
        return self._change(changed)

    def _trail(self) -> list[JSONish]:
        """Every event now: each server's History and the seeded ones."""
        self._read()
        histories = [e for row in self._rows.values() for e in self._records.history(row)]
        return histories + [dict(event) for event in self._events]

    def _carried_skill(self) -> Skill:
        self._read()
        if self._skill is None:
            raise ServerScanSkillMissingError(
                "server-scan: This deployment carries no Claude Code skill. (fake)"
            )
        return self._skill

    def _writable(self, server_id: str) -> ServerRow:
        self._read()
        row = self._rows.get(server_id)
        if row is None:
            raise ServerNotFoundError(f"server-scan has no server {server_id!r} (fake)")
        return row

    def _host(self, row: ServerRow) -> VmHostServer:
        record = self._records.record(row, self._clock())
        return VmHostServer(
            id=row.id,
            name=row.name,
            vendor=record.identity.vendor,
            model=row.model,
            site_id=row.site,
            cpu=record.hardware.cpu,
            memory_total_bytes=record.hardware.memory.total_bytes,
            health=row.health,
            maintenance=row.maintenance,
            cluster_name=row.cluster_name,
        )

    def _change(self, row: ServerRow) -> ServerMaintenance:
        self._rows[row.id] = row
        return ServerMaintenance(
            server_id=row.id,
            server_name=row.name,
            enabled=row.maintenance,
            reason=row.maintenance_reason,
            created_by=row.maintenance_by,
        )

    def _read(self) -> None:
        if self.unavailable:
            raise ServerScanUnavailableError("server-scan unreachable (fake)")
        for hook in self._before_read:
            hook()


@dataclass(slots=True)
class _Run:
    workflow_id: str
    server_id: str | None
    started: datetime
    status: str = "running"
    phase: str | None = None
    error: str | None = None
    walks: bool = True
    """Whether it moves on with the clock; a seeded run stays as it was seeded."""


class FakeUninstallWorkflow:
    """An ``UninstallWorkflow`` whose runs walk the demo phases and then free their server."""

    def __init__(
        self,
        inventory: FakeServerInventory,
        *,
        clock: Clock = system_clock,
        runs: Iterable[WorkflowRun] = (),
        unavailable: bool = False,
    ) -> None:
        """Act on ``inventory``; ``runs`` are seeded as they are (newest first) and never move."""
        self._inventory = inventory
        self._clock = clock
        self._runs: list[_Run] = [
            _Run(r.workflow_id, None, clock(), r.status, r.phase, r.error, walks=False)
            for r in reversed(list(runs))
        ]
        self.unavailable = unavailable
        self.fail_start: WorkflowsError | None = None
        """When set, ``start`` raises it (an ambiguous or refused start, for tests)."""
        self.starts: list[dict[str, str | None]] = []
        """Every start's input, in order."""
        self._completed: list[Callable[[str], object]] = []
        inventory.before_read(self._advance)

    def after_uninstall(self, hook: Callable[[str], object]) -> None:
        """Call ``hook(server_name)`` when a run completes: the fake MCE drops its node."""
        self._completed.append(hook)

    async def runs(self) -> list[RunSummary]:
        """See UninstallWorkflow.runs."""
        self._check()
        return [RunSummary(r.workflow_id, r.status) for r in reversed(self._runs)]

    async def run(self, workflow_id: str) -> WorkflowRun | None:
        """See UninstallWorkflow.run."""
        self._check()
        found = next((r for r in reversed(self._runs) if r.workflow_id == workflow_id), None)
        if found is None:
            return None
        return WorkflowRun(found.workflow_id, found.status, phase=found.phase, error=found.error)

    async def start(self, *, server_name: str, mce: str, namespace: str | None) -> WorkflowRun:
        """See UninstallWorkflow.start."""
        self._check()
        self.starts.append({"server_name": server_name, "mce": mce, "namespace": namespace})
        if self.fail_start is not None:
            raise self.fail_start
        workflow_id = uninstall_workflow_id(server_name)
        if any(r.workflow_id == workflow_id and r.status == "running" for r in self._runs):
            raise UninstallAlreadyRunningError(f"an uninstall of {server_name} is already running")
        server = self._inventory.by_name(server_name)
        run = _Run(workflow_id, server.id if server else None, self._clock())
        if server is None:
            run.status, run.phase = "failed", DEMO_PHASES[0]
            run.error = f"ServerNotFoundError: server-scan has no server named {server_name} (fake)"
        else:
            run.phase = DEMO_PHASES[0]
            self._inventory.replace(dataclasses.replace(server, reserved_by=UNINSTALL_HOLDER))
        self._runs.append(run)
        return WorkflowRun(workflow_id, "running")

    def _check(self) -> None:
        if self.unavailable:
            raise WorkflowsUnavailableError("the orchestrator is unreachable (fake)")
        self._advance()

    def _advance(self) -> None:
        now = self._clock()
        for run in self._runs:
            if not run.walks or run.status != "running":
                continue
            step = int((now - run.started).total_seconds() // PHASE_SECONDS)
            if step < len(DEMO_PHASES):
                run.phase = DEMO_PHASES[step]
                continue
            run.status, run.phase = "completed", "completed"
            server = self._inventory.by_id(run.server_id) if run.server_id else None
            if server is not None:  # it leaves the cluster, then the MCE: free in server-scan
                self._inventory.replace(
                    dataclasses.replace(
                        server, state="AVAILABLE", cluster_name=None, mce=None, reserved_by=None
                    )
                )
                for hook in self._completed:
                    hook(server.name)


def default_fleet_file() -> Path:
    """``dev/fleet-fixtures/servers.yaml`` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / FLEET_FILE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{FLEET_FILE} not found above this file")


def load_fleet(path: Path) -> tuple[list[ServerRow], list[WorkflowRun]]:
    """The servers (``items``, in server-scan's row shape) and seeded ``runs`` of a fixture."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise TypeError(f"{path}: expected a mapping with an 'items' list")
    rows = [server_row(item) for item in raw["items"]]
    names = {row.name.lower() for row in rows}
    runs: list[WorkflowRun] = []
    for item in raw.get("runs") or []:
        server = item["server"]
        if server.lower() not in names:
            raise ValueError(f"{path}: a run names {server!r}, which is not in items")
        runs.append(
            WorkflowRun(
                uninstall_workflow_id(server),
                str(item["status"]).lower(),
                phase=item.get("phase"),
                error=item.get("error"),
            )
        )
    return rows, runs
