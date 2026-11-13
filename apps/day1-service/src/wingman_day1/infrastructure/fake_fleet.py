"""FakeServerInventory and FakeUninstallWorkflow: server-scan and the orchestrator in memory.

Tests seed them directly; ``DAY1_FAKE_FLEET=true`` (development only) seeds
them from ``dev/fleet-fixtures/servers.yaml``, written in server-scan's own
row shape and read by the HTTP adapter's parser. They raise the same domain
errors as the real adapters. The fake's sites are its rows counted by
server-scan's rules over a site catalog (``fake_server_scan_sites``, ADR-0048).

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
    ServerScanUnavailableError,
    UninstallAlreadyRunningError,
    WorkflowsError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.domain.servers import (
    UNINSTALL_HOLDER,
    RunSummary,
    ServerDetail,
    ServerRow,
    uninstall_workflow_id,
)
from wingman_day1.domain.workflows import WorkflowRun
from wingman_day1.infrastructure.fake_server_scan_sites import SiteName, catalog_of, count_sites
from wingman_day1.infrastructure.server_scan import server_row

DEMO_PHASES: Final = (
    "checking-inventory",
    "draining-node",
    "awaiting-machine-deletion",
    "removing-from-inventory",
)
"""A few of the real workflow's steps, for the demo only."""
PHASE_SECONDS: Final = 8.0
FLEET_FILE: Final = Path("dev/fleet-fixtures/servers.yaml")


class FakeServerInventory:
    """A ``ServerInventory`` over seeded rows; ``unavailable`` fails every call, as if down."""

    def __init__(
        self,
        rows: Iterable[ServerRow] = (),
        *,
        unavailable: bool = False,
        sites: Sequence[SiteName] = (),
    ) -> None:
        """Seed the fleet; ``sites`` is server-scan's site catalog (none: the rows' own sites)."""
        self._rows = {row.id: row for row in rows}
        self.unavailable = unavailable
        self._sites = tuple(sites)
        self.server_reads = 0
        """How many times ``server`` was called (the uninstall's fresh read)."""
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
        self._read()
        return sorted(self._rows.values(), key=lambda row: row.name)

    async def server(self, server_id: str) -> ServerDetail:
        """See ServerInventory.server."""
        self._read()
        self.server_reads += 1
        row = self._rows.get(server_id)
        if row is None:
            raise ServerNotFoundError(f"server-scan has no server {server_id!r} (fake)")
        return ServerDetail(id=row.id, name=row.name, cluster_name=row.cluster_name)

    async def sites(self) -> FleetSites:
        """See ServerInventory.sites: the rows now, counted as server-scan counts them."""
        self._read()
        rows = list(self._rows.values())
        return count_sites(rows, self._sites or catalog_of(rows))

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
