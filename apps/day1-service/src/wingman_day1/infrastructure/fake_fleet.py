"""FakeUninstallWorkflow, the orchestrator's uninstall in memory, and the fleet fixture.

``load_fleet`` reads ``dev/fleet-fixtures/servers.yaml``: the servers, in
server-scan's row shape, that seed ``FakeServerInventory``
(``fake_server_inventory``), and the seeded uninstall runs. Tests seed both
fakes directly; ``DAY1_FAKE_FLEET=true`` (development only) seeds them from
the fixture. They raise the same domain errors as the real adapters.

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
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

import yaml

from wingman_core.ports.clock import Clock, system_clock
from wingman_day1.domain.errors import (
    UninstallAlreadyRunningError,
    WorkflowsError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.servers import (
    UNINSTALL_HOLDER,
    RunSummary,
    ServerRow,
    uninstall_workflow_id,
)
from wingman_day1.domain.workflows import WorkflowRun
from wingman_day1.integrations.server_scan.infrastructure.fakes.inventory import FakeServerInventory
from wingman_day1.integrations.server_scan.infrastructure.parse import server_row

DEMO_PHASES: Final = (
    "checking-inventory",
    "draining-node",
    "awaiting-machine-deletion",
    "removing-from-inventory",
)
"""A few of the real workflow's steps, for the demo only."""
PHASE_SECONDS: Final = 8.0


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
