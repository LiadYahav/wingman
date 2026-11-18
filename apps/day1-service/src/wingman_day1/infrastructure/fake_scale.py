"""FakeScaleWorkflow: the update-nodepool workflow, in memory (ADR-0062).

Tests seed it directly; with ``DAY1_FAKE_FLEET=true`` (development only) it
reads a cluster's NodePools from its day1 file (``compose_scale``). It raises
the same domain errors as the real adapter: a second start while a run of
the cluster runs, or while its upgrade runs, is ``ScaleAlreadyRunningError``.

A run walks the parent's phases and then its child's on the injected clock.
The phases, the plan (the one NodePool set exactly) and the servers a
scale-down picks (the named ones, else by the run's policy, else by the
NodePool's) are a sample for the demo, nothing more: day1 passes the
real workflow's through and plans nothing itself. Nothing is written
anywhere; the fake only remembers the replicas its runs left, for its next
run.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from wingman_core.ports.clock import Clock, system_clock
from wingman_day1.domain.errors import ScaleAlreadyRunningError, WorkflowsUnavailableError
from wingman_day1.domain.scale import (
    ChosenServer,
    NodePoolChange,
    ScaleChild,
    ScaleRequest,
    ScaleResult,
    ScaleRun,
    scale_workflow_id,
)

PARENT_PHASES: Final = ("pending", "reading-day1", "reading-nodepools", "planning")
UP_PHASES: Final = ("committing-day1", "syncing-argo", "verifying-nodepools")
DOWN_PHASES: Final = (
    "selecting-servers",
    "marking-machines",
    "committing-day1",
    "syncing-argo",
    "verifying-nodepools",
    "verifying-machines",
)
REVISION: Final = "f4ce0000000000000000000000000000000000ff"


@dataclass(frozen=True, slots=True)
class FakePool:
    """One NodePool of a cluster, as the fake MCE would show it."""

    name: str
    infra_env: str | None
    replicas: int
    scale_down_policy: str | None = None


PoolSource = Callable[[str], Awaitable[Sequence[FakePool]]]
"""A cluster file's stem → its NodePools."""


@dataclass(slots=True)
class _Run:
    request: ScaleRequest
    started: datetime
    changes: tuple[NodePoolChange, ...] = ()
    refusal: str | None = None
    applied: bool = False
    chosen: tuple[ChosenServer, ...] = field(default=())
    ignored: tuple[str, ...] = ()


class FakeScaleWorkflow:
    """A ``ScaleWorkflow`` whose runs walk sample phases and plan a sample spread."""

    def __init__(
        self,
        *,
        clock: Clock = system_clock,
        pools: PoolSource | None = None,
        phase_seconds: float = 4.0,
        upgrading: Callable[[str], bool] | None = None,
        unavailable: bool = False,
    ) -> None:
        """``upgrading(cluster)`` says whether an upgrade of it runs (the orchestrator's 409)."""
        self._clock = clock
        self._pools = pools
        self._step = phase_seconds
        self._upgrading = upgrading or (lambda _cluster: False)
        self._unavailable = unavailable
        self._runs: dict[str, _Run] = {}
        self._left: dict[tuple[str, str], int] = {}
        self.started: list[ScaleRequest] = []
        """Every start the fake accepted, in order (for tests)."""

    def read_pools_with(self, pools: PoolSource) -> None:
        """Where the fake reads a cluster's NodePools from (the fake fleet's day1 files)."""
        self._pools = pools

    async def start(self, request: ScaleRequest) -> ScaleRun:
        """See ScaleWorkflow.start."""
        if self._unavailable:
            raise WorkflowsUnavailableError("the fake orchestrator is down; nothing was started")
        cluster = request.cluster
        if self._upgrading(cluster):
            raise ScaleAlreadyRunningError(
                f"upgrade-cluster-{cluster} is running: a replicas commit now would change the "
                "file under the upgrade, which would stop for a person at its next commit. Run "
                "update-nodepool once the upgrade has finished"
            )
        previous = self._runs.get(cluster)
        if previous is not None and self._view(previous).status == "running":
            raise ScaleAlreadyRunningError(
                f"An update-nodepool run is already in flight for cluster {cluster}"
            )
        pools = [self._now(cluster, p) for p in await self._read(cluster)]
        run = _Run(request=request, started=self._clock())
        _plan(run, pools)
        self._runs[cluster] = run
        self.started.append(request)
        return ScaleRun(workflow_id=scale_workflow_id(cluster), status="running")

    async def run(self, workflow_id: str) -> ScaleRun | None:
        """See ScaleWorkflow.run."""
        if self._unavailable:
            raise WorkflowsUnavailableError("the fake orchestrator is down")
        run = next(
            (r for r in self._runs.values() if scale_workflow_id(r.request.cluster) == workflow_id),
            None,
        )
        return None if run is None else self._view(run)

    # ── Internals ───────────────────────────────────────────────────────────

    async def _read(self, cluster: str) -> Sequence[FakePool]:
        return await self._pools(cluster) if self._pools is not None else ()

    def _now(self, cluster: str, pool: FakePool) -> FakePool:
        left = self._left.get((cluster, pool.name))
        if left is None:
            return pool
        return FakePool(pool.name, pool.infra_env, left, pool.scale_down_policy)

    def _view(self, run: _Run) -> ScaleRun:
        workflow_id = scale_workflow_id(run.request.cluster)
        step = int((self._clock() - run.started).total_seconds() // self._step)
        if step < len(PARENT_PHASES):
            if run.refusal is not None and step >= PARENT_PHASES.index("reading-nodepools"):
                return ScaleRun(workflow_id, "failed", "reading-nodepools", error=run.refusal)
            return ScaleRun(workflow_id, "running", PARENT_PHASES[step])
        if run.refusal is not None:
            return ScaleRun(workflow_id, "failed", "reading-nodepools", error=run.refusal)
        direction = _direction(run.changes)
        child_phases = DOWN_PHASES if direction == "down" else UP_PHASES
        child_step = step - len(PARENT_PHASES)
        if direction != "none" and child_step < len(child_phases):
            child = ScaleChild(
                f"scale-{direction}-nodepool-{run.request.cluster}",
                "running",
                child_phases[child_step],
            )
            return ScaleRun(workflow_id, "running", f"scaling-{direction}", direction, child)
        if not run.applied:
            run.applied = True
            for change in run.changes:
                if change.after is not None:
                    self._left[(run.request.cluster, change.name)] = change.after
        return ScaleRun(workflow_id, "completed", "completed", direction, result=_result(run))


def _direction(changes: Sequence[NodePoolChange]) -> str:
    if any((c.after or 0) < (c.before or 0) for c in changes):
        return "down"
    if any((c.after or 0) > (c.before or 0) for c in changes):
        return "up"
    return "none"


def _plan(run: _Run, pools: Sequence[FakePool]) -> None:
    """The sample plan, or the refusal the run will fail with."""
    request = run.request
    selected = [p for p in pools if p.name == request.nodepool]
    if not selected:
        names = ", ".join(sorted(p.name for p in pools)) or "none"
        run.refusal = (
            f"the cluster has no NodePool {request.nodepool}, on the MCE or in day1; its "
            f"NodePools are {names}. Nothing was written"
        )
        return
    pool = selected[0]
    down = request.replicas < pool.replicas
    if down and request.server_names:
        policy = None
    else:
        policy = (request.scale_down_policy if down else None) or pool.scale_down_policy
    run.changes = (
        NodePoolChange(pool.name, pool.infra_env, pool.replicas, request.replicas, policy),
    )
    run.chosen = tuple(
        ChosenServer(
            pool.name, f"{pool.name}-m{n}", f"{pool.name}-worker-{n}", policy, "0 workload pods"
        )
        for n in range(request.replicas, pool.replicas)
        if policy
    )
    if down and request.server_names:
        run.chosen = tuple(_named(request.nodepool, request.server_names))
    if not down and request.scale_down_policy is not None:
        why = (
            "the NodePool scales up" if request.replicas > pool.replicas else "nothing scales down"
        )
        run.ignored = (f"scale_down_policy {request.scale_down_policy}: {why}",)


def _named(nodepool: str, names: Sequence[str]) -> Iterator[ChosenServer]:
    """A scale-down that names its servers: exactly those leave, each its own Machine."""
    for n, name in enumerate(names):
        server = name.lower()
        yield ChosenServer(nodepool, f"{nodepool}-m{n}", server, "named", f"named: {name}", server)


def _result(run: _Run) -> ScaleResult:
    request, changes = run.request, run.changes
    direction = _direction(changes)
    return ScaleResult(
        direction=direction,
        nodepool=request.nodepool,
        total_before=sum(c.before or 0 for c in changes),
        total_after=sum(c.after or 0 for c in changes),
        nodepools=changes,
        child_workflow_id=(
            f"scale-{direction}-nodepool-{request.cluster}" if direction != "none" else None
        ),
        revision=REVISION if direction != "none" else None,
        committed=direction != "none" or None,
        chosen=run.chosen,
        deleting=tuple(c.machine for c in run.chosen),
        ignored=run.ignored,
    )
