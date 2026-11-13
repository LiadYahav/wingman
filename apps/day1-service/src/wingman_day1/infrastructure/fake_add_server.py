"""FakeAddServerWorkflow: the add-server-to-mce workflow, and a herzi, in memory (ADR-0057).

Tests seed it directly; ``DAY1_FAKE_FLEET=true`` (development only) seeds it
from ``dev/fleet-fixtures/inventory.yaml``. It raises the same domain errors
as the real adapter.

A run walks a few sample phases on the injected clock. At its second phase
it takes a server in the fake server-scan, as the workflow takes server-scan's
lock: a pool draw the first ``AVAILABLE``, healthy, reachable, unlocked server
out of maintenance named ``ocp-<infraEnv>``; a named install its server, and
it fails as the workflow fails (locked, in maintenance, contested, not
``AVAILABLE``). Done, the server is in the MCE's inventory. The phases are a
sample for the demo, nothing more: day1 passes the real workflow's through.

The fake herzi starts a pool draw on one pool now and then; after a run of
its fails for want of servers, it waits longer (as herzi's probe mode). Its
runs look like a person's pool draws, as on the real orchestrator.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from wingman_core.ports.clock import Clock, system_clock
from wingman_day1.domain.add_server import (
    ADD_SERVER_WORKFLOW_PREFIX,
    MAX_SLOT,
    AddServerRequest,
    AddServerRun,
    AddServerStart,
    ListedRun,
    StartedRun,
    canonical_mce,
)
from wingman_day1.domain.errors import (
    AddServerAlreadyRunningError,
    WorkflowsError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.inventory import AVAILABLE_STATE, drawable, named_for, why_not
from wingman_day1.domain.mce_capacity import SPARE_STATE
from wingman_day1.domain.servers import ServerRow
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory

HOLDER: Final = "add-server-to-mce"
DEMO_PHASES: Final = ("validating-infraenv", "acquiring-server", "registering-bmh")
"""A few of the real workflow's steps, for the demo only."""
TAKE_STEP: Final = 1
"""The phase at which a run takes its server."""
INSTALL_LOCK: Final = timedelta(hours=2)
DONE_LOCK: Final = timedelta(hours=24)
KEPT_RUNS: Final = 200
"""The most runs kept, as the orchestrator's list returns."""


@dataclass(frozen=True, slots=True)
class HerziScript:
    """Where the fake herzi orders servers, and how often."""

    mce: str
    infra_env: str
    first_after: timedelta
    every: timedelta
    probe: timedelta
    """After a run of its finds no server, how long it waits before the next."""


@dataclass(slots=True)
class FakeRun:
    """One run; ``walks`` is ``False`` for a seeded one, which stays as it was seeded."""

    workflow_id: str
    mce: str
    infra_env: str
    started: datetime
    server: str | None = None
    named: bool = False
    status: str = "running"
    phase: str | None = None
    error: str | None = None
    closed: datetime | None = None
    walks: bool = True
    herzi: bool = False
    taken: bool = False
    """Whether it has taken its server (server-scan's lock)."""


class FakeAddServerWorkflow:
    """An ``AddServerWorkflow`` whose runs take servers in the fake server-scan."""

    def __init__(
        self,
        inventory: FakeServerInventory,
        *,
        clock: Clock = system_clock,
        phases: Iterable[str] = DEMO_PHASES,
        phase_seconds: float = 8.0,
        herzi: HerziScript | None = None,
        runs: Iterable[FakeRun] = (),
        unavailable: bool = False,
    ) -> None:
        """Act on ``inventory``; ``runs`` are seeded as they are, in any order."""
        self._inventory = inventory
        self._clock = clock
        self._phases = tuple(phases)
        self._step = timedelta(seconds=phase_seconds)
        self._runs = sorted((dataclasses.replace(r, walks=False) for r in runs), key=_start)
        self.unavailable = unavailable
        self.fail_start: WorkflowsError | None = None
        """When set, ``start`` raises it (an ambiguous or refused start, for tests)."""
        self.starts: list[AddServerRequest] = []
        self._herzi = herzi
        self._herzi_next = clock() + herzi.first_after if herzi else None
        self._herzi_wait_until: datetime | None = None
        inventory.before_read(self._advance)

    async def runs(self) -> list[ListedRun]:
        """See AddServerWorkflow.runs."""
        self._check()
        return [
            ListedRun(r.workflow_id, r.status, started_at=r.started, closed_at=r.closed)
            for r in reversed(self._runs)
        ]

    async def run(self, workflow_id: str) -> AddServerRun | None:
        """See AddServerWorkflow.run."""
        self._check()
        found = next((r for r in reversed(self._runs) if r.workflow_id == workflow_id), None)
        if found is None:
            return None
        return AddServerRun(found.workflow_id, found.status, found.phase, found.server, found.error)

    async def start(self, request: AddServerRequest) -> AddServerStart:
        """See AddServerWorkflow.start."""
        self._check()
        self.starts.append(request)
        if self.fail_start is not None:
            raise self.fail_start
        now = self._clock()
        if request.count is not None:
            runs = [
                self._pool_run(request.mce, request.infra_env, now) for _ in range(request.count)
            ]
            if all(run is None for run in runs):
                raise AddServerAlreadyRunningError(
                    f"every slot of {request.infra_env} is busy (fake)"
                )
            answers = [_answer(run) for run in runs if run is not None]
        else:
            answers = [self._named(request, name, now) for name in request.server_names]
        return AddServerStart(
            started=sum(1 for a in answers if a.status == "started"),
            already_running=sum(1 for a in answers if a.status == "already_running"),
            failed=0,
            runs=tuple(answers),
        )

    def _named(self, request: AddServerRequest, name: str, now: datetime) -> StartedRun:
        mce = canonical_mce(request.mce)
        workflow_id = f"{ADD_SERVER_WORKFLOW_PREFIX}{mce}_{name.lower()}"
        if any(r.workflow_id == workflow_id and r.status == "running" for r in self._runs):
            return StartedRun(workflow_id, "already_running", server_name=name)
        run = FakeRun(workflow_id, mce, request.infra_env, now, server=name, named=True)
        self._add(run)
        return StartedRun(workflow_id, "started", server_name=name)

    def _pool_run(
        self, mce: str, infra_env: str, at: datetime, *, herzi: bool = False
    ) -> FakeRun | None:
        mce = canonical_mce(mce)
        prefix = f"{ADD_SERVER_WORKFLOW_PREFIX}{mce}_{infra_env}_"
        busy = {r.workflow_id for r in self._runs if r.status == "running"}
        slot = next((s for s in range(1, MAX_SLOT + 1) if f"{prefix}{s}" not in busy), None)
        if slot is None:
            return None
        run = FakeRun(f"{prefix}{slot}", mce, infra_env, at, herzi=herzi)
        self._add(run)
        return run

    def _add(self, run: FakeRun) -> None:
        run.phase = self._phases[0] if self._phases else None
        self._runs.append(run)
        del self._runs[:-KEPT_RUNS]

    def _check(self) -> None:
        if self.unavailable:
            raise WorkflowsUnavailableError("the orchestrator is unreachable (fake)")
        self._advance()

    def _advance(self) -> None:
        now = self._clock()
        while self._herzi is not None and self._herzi_next is not None and self._herzi_next <= now:
            at = self._herzi_next
            self._walk(at)
            if self._herzi_wait_until is not None and at < self._herzi_wait_until:
                self._herzi_next = self._herzi_wait_until
                continue
            self._pool_run(self._herzi.mce, self._herzi.infra_env, at, herzi=True)
            self._herzi_next = at + self._herzi.every
        self._walk(now)

    def _walk(self, now: datetime) -> None:
        for run in self._runs:
            if not run.walks or run.status != "running" or run.started > now:
                continue
            step = int((now - run.started) / self._step)
            if step >= TAKE_STEP and not run.taken:
                self._take(run, run.started + TAKE_STEP * self._step)
                if run.status != "running":
                    continue
            if step < len(self._phases):
                run.phase = self._phases[step]
                continue
            self._finish(run, run.started + len(self._phases) * self._step)

    def _take(self, run: FakeRun, at: datetime) -> None:
        row = self._candidate(run)
        if isinstance(row, str):
            self._fail(run, at, row)
            return
        run.server, run.taken = row.name, True
        self._inventory.replace(
            dataclasses.replace(
                row,
                reserved_by=HOLDER,
                reserved_for_mce=run.mce,
                reserved_for_infra_env=run.infra_env,
                reserved_until=at + INSTALL_LOCK,
            )
        )

    def _candidate(self, run: FakeRun) -> ServerRow | str:
        """The run's server, or the error it fails with."""
        if not run.named:
            rows = self._inventory.snapshot()
            found = next(
                (
                    row
                    for row in rows
                    if row.state == AVAILABLE_STATE
                    and named_for(row.name, run.infra_env)
                    and drawable(row)
                ),
                None,
            )
            if found is None:
                return (
                    f"ServerNotAvailableError: no healthy free server named "
                    f"^ocp-{run.infra_env} (fake)"
                )
            return found
        row = self._inventory.by_name(run.server or "")
        if row is None or row.state != AVAILABLE_STATE:
            return f"ServerNotAvailableError: {run.server} is not AVAILABLE (fake)"
        reason = why_not(row)
        if reason is not None and row.reserved_by is not None:
            return f"ServerReservedError: {run.server} is {reason} (fake)"
        if reason is not None:
            return f"ServerNotAvailableError: {run.server} is {reason} (fake)"
        return row

    def _fail(self, run: FakeRun, at: datetime, error: str) -> None:
        run.status, run.error, run.closed = "failed", error, at
        if run.herzi and self._herzi is not None:
            self._herzi_wait_until = at + self._herzi.probe

    def _finish(self, run: FakeRun, at: datetime) -> None:
        run.status, run.phase, run.closed = "completed", "completed", at
        row = self._inventory.by_name(run.server or "")
        if row is not None:
            self._inventory.replace(
                dataclasses.replace(
                    row, state=SPARE_STATE, mce=run.mce, reserved_until=at + DONE_LOCK
                )
            )


def _start(run: FakeRun) -> datetime:
    return run.started


def _answer(run: FakeRun) -> StartedRun:
    slot = int(run.workflow_id.rsplit("_", 1)[1])
    return StartedRun(run.workflow_id, "started", slot=slot)
