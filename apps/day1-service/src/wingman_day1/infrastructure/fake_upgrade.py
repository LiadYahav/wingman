"""FakeUpgradeWorkflow: the upgrade-cluster workflow in memory (ADR-0055).

Tests drive it directly; ``DAY1_FAKE_FLEET=true`` (development only) seeds
it from ``dev/fleet-fixtures/upgrade.yaml``, so the local demo can start an
upgrade and walk it to done. Its targets are the fixture's, in the
orchestrator's shape and read by the real parser. A started run walks the
fixture's steps on the injected clock: a step with ``seconds`` moves on by
itself, one with ``waits_for`` waits for that decision, and any other
decision is refused as the run's validator would (a 409, in words). The
steps and their texts are fixture data, a sample for the demo: day1 passes
the real workflow's phases through and keeps no list of them. ``seed``
starts the fixture's demo runs, so the fleet's list has something to show.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Final

from wingman_core.ports.clock import Clock, system_clock
from wingman_day1.domain.add_server import ListedRun
from wingman_day1.domain.errors import (
    ResourceNotFoundError,
    UpgradeAlreadyRunningError,
    UpgradeDecisionRefusedError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.upgrades import (
    LogLine,
    PlanStep,
    UpgradeDecision,
    UpgradePlan,
    UpgradeRequest,
    UpgradeRun,
    UpgradeTargets,
    upgrade_workflow_id,
)
from wingman_day1.infrastructure.fake_upgrade_script import ScriptStep, UpgradeScript

LOG_LINES: Final = 20
"""The workflow keeps its last 20 log lines."""


@dataclass(slots=True)
class _Step:
    script: ScriptStep
    section: str
    nodepool: str | None


@dataclass(slots=True)
class _Run:
    request: UpgradeRequest
    targets: UpgradeTargets
    target: str
    steps: list[_Step]
    since: datetime
    """When the current step began (once closed: when it closed)."""
    started: datetime
    position: int = 0
    approved: bool = False
    paused_by: str | None = None
    outcome: str | None = None
    control_plane: str = ""
    nodepools: dict[str, str] = field(default_factory=dict)
    done: list[str] = field(default_factory=list)
    log: list[LogLine] = field(default_factory=list)


class FakeUpgradeWorkflow:
    """An ``UpgradeWorkflow`` whose runs walk the fixture's steps on the clock."""

    def __init__(self, script: UpgradeScript, *, clock: Clock = system_clock) -> None:
        """Answer from ``script``; ``unavailable`` (settable) fails every call, as if down."""
        self._script = script
        self._clock = clock
        self._runs: dict[str, _Run] = {}
        self.unavailable = False
        self.starts: list[UpgradeRequest] = []
        self.decisions: list[tuple[str, str, str, str | None]] = []
        """Every decision sent: ``(workflow_id, decision, by, reason)``."""

    async def targets(self, cluster: str) -> UpgradeTargets:
        """See UpgradeWorkflow.targets."""
        self._check()
        return self._targets(cluster)

    async def start(self, request: UpgradeRequest) -> UpgradeRun:
        """See UpgradeWorkflow.start."""
        self._check()
        self.starts.append(request)
        return self._begin(request)

    async def runs(self) -> list[ListedRun]:
        """See UpgradeWorkflow.runs: one entry per run, newest first."""
        self._check()
        listed = []
        for workflow_id, run in self._runs.items():
            self._tick(run)
            closed = run.since if run.outcome is not None else None
            status = "running" if closed is None else "completed"
            listed.append(ListedRun(workflow_id, status, started_at=run.started, closed_at=closed))
        return sorted(
            listed, key=lambda r: r.started_at.timestamp() if r.started_at else 0.0, reverse=True
        )

    def seed(self, request: UpgradeRequest, decisions: Sequence[UpgradeDecision] = ()) -> None:
        """Start a demo run now, and send it ``decisions`` as soon as it waits for each."""
        workflow_id = self._begin(request).workflow_id
        run = self._runs[workflow_id]
        for decision in decisions:
            run.since -= timedelta(minutes=1)  # the timed steps before it are over
            self._decide(workflow_id, decision, by=request.requested_by, reason="demo")
        run.started = self._clock() - timedelta(minutes=len(decisions) + 1)

    def _begin(self, request: UpgradeRequest) -> UpgradeRun:
        workflow_id = upgrade_workflow_id(request.cluster)
        if (open_run := self._runs.get(workflow_id)) is not None and open_run.outcome is None:
            raise UpgradeAlreadyRunningError(f"{request.cluster} already has an upgrade run")
        targets = self._targets(request.cluster)
        target = request.target_version or _newest(targets, request.target_minor) or ""
        order = list(request.nodepool_order or targets.nodepool_order) or [
            pool.name for pool in targets.nodepools
        ]
        if request.workers_to_target is False:
            order = []
        run = _Run(
            request=request,
            targets=targets,
            target=target,
            steps=self._flatten(order),
            since=self._clock(),
            started=self._clock(),
            control_plane=targets.control_plane_version or "",
            nodepools=dict.fromkeys(order, targets.control_plane_version or ""),
        )
        self._runs[workflow_id] = run
        self._note(run, "started", request.requested_by, f"toward {target}")
        return UpgradeRun(workflow_id=workflow_id, status="running")

    async def run(self, workflow_id: str) -> UpgradeRun | None:
        """See UpgradeWorkflow.run."""
        self._check()
        run = self._runs.get(workflow_id)
        return None if run is None else self._view(workflow_id, run)

    async def decide(
        self,
        workflow_id: str,
        decision: UpgradeDecision,
        *,
        by: str,
        reason: str | None = None,
        nodepool: str | None = None,
    ) -> None:
        """See UpgradeWorkflow.decide: the run takes what it waits for, and pause, resume, abort."""
        self._check()
        self._decide(workflow_id, decision, by=by, reason=reason, nodepool=nodepool)

    def _decide(
        self,
        workflow_id: str,
        decision: UpgradeDecision,
        *,
        by: str,
        reason: str | None = None,
        nodepool: str | None = None,
    ) -> None:
        run = self._open(workflow_id)
        self.decisions.append((workflow_id, decision.value, by, reason))
        if decision is UpgradeDecision.ABORT:
            run.outcome = "aborted" if run.approved else "cancelled"
            run.since = self._clock()
        elif decision in (UpgradeDecision.PAUSE, UpgradeDecision.RESUME):
            self._pause(run, decision, by)
        elif run.paused_by is None and decision is run.steps[run.position].script.waits_for:
            if nodepool and decision is UpgradeDecision.CONTINUE:
                self._roll_next(run, nodepool)
            run.approved = run.approved or decision is UpgradeDecision.APPROVE
            self._advance(run, self._clock())
        else:
            raise self._refusal(run, decision.value)
        self._note(run, decision.value, by, reason or nodepool or "")

    async def decide_action(
        self, workflow_id: str, action_id: str, *, approve: bool, by: str
    ) -> None:
        """See UpgradeWorkflow.decide_action: the fake's agent never proposes anything."""
        self._check()
        run = self._open(workflow_id)
        raise UpgradeDecisionRefusedError(
            f"no pending action {action_id}: {self._refusal(run, 'the action')}"
        )

    # ── Internals ───────────────────────────────────────────────────────────

    def _targets(self, cluster: str) -> UpgradeTargets:
        found = self._script.targets.get(cluster) or self._script.targets.get("default")
        if found is None:
            raise ResourceNotFoundError(f"the fake's day1 has no {cluster}")
        return replace(found, cluster=cluster)

    def _flatten(self, order: Sequence[str]) -> list[_Step]:
        steps = self._script.steps
        flat = [_Step(s, "before", None) for s in steps.get("before", ())]
        flat += [_Step(s, "control_plane", None) for s in steps.get("control_plane", ())]
        for pool in order:
            flat += [_Step(s, "each_nodepool", pool) for s in steps.get("each_nodepool", ())]
        return flat + [_Step(s, "after", None) for s in steps.get("after", ())]

    def _open(self, workflow_id: str) -> _Run:
        run = self._runs.get(workflow_id)
        if run is not None:
            self._tick(run)
        if run is None or run.outcome is not None:
            raise ResourceNotFoundError(f"no running upgrade-cluster run {workflow_id}")
        return run

    def _pause(self, run: _Run, decision: UpgradeDecision, by: str) -> None:
        pausing = decision is UpgradeDecision.PAUSE
        if not run.approved or (run.paused_by is not None) is pausing:
            raise self._refusal(run, decision.value)
        run.paused_by = by if pausing else None
        run.since = self._clock()

    def _roll_next(self, run: _Run, nodepool: str) -> None:
        """``continue`` naming a NodePool: it rolls now, the others keep their order."""
        current = run.steps[run.position].nodepool
        rest = list(dict.fromkeys(s.nodepool for s in run.steps[run.position :] if s.nodepool))
        if nodepool not in rest:
            raise UpgradeDecisionRefusedError(f"continue: {nodepool} is not waiting to roll")
        if nodepool != current:
            order = [*run.done, nodepool, *(p for p in rest if p != nodepool)]
            position = run.position
            run.steps = self._flatten(order)
            run.position = position

    def _advance(self, run: _Run, since: datetime) -> None:
        """The step is over: its version moves, and the next one starts at ``since``."""
        step = run.steps[run.position]
        if step.script.moves == "control-plane":
            run.control_plane = run.target
        elif step.script.moves == "nodepool" and step.nodepool:
            run.nodepools[step.nodepool] = run.target
        if step.nodepool and _last_of_pool(run, run.position):
            run.done.append(step.nodepool)
        run.position += 1
        run.since = since
        if run.position >= len(run.steps):
            run.outcome = "done"

    def _tick(self, run: _Run) -> None:
        """Walk every step whose time is up, each starting when the one before ended."""
        while run.outcome is None and run.paused_by is None:
            step = run.steps[run.position].script
            ends = run.since + timedelta(seconds=step.seconds)
            if step.waits_for is not None or ends > self._clock():
                return
            self._advance(run, ends)

    def _view(self, workflow_id: str, run: _Run) -> UpgradeRun:
        self._tick(run)
        closed = UpgradeRun(
            workflow_id,
            "completed",
            mce=run.targets.mce or None,
            plan=_plan(run),
            control_plane_version=run.control_plane,
            nodepool_versions=dict(run.nodepools),
            log=tuple(run.log),
            outcome=run.outcome,
            steps_completed=_steps_completed(run),
        )
        if run.outcome is not None:
            return closed
        step = run.steps[run.position]
        return replace(
            closed,
            status="running",
            outcome=None,
            steps_completed=None,
            phase="paused" if run.paused_by else step.script.phase,
            waiting_for=(
                f"resume: paused by {run.paused_by}" if run.paused_by else self._text(run, step)
            ),
            profile="generic",
            current_step=_plan_step(step),
            current_nodepool=step.nodepool,
            nodepools_done=tuple(run.done),
            paused=run.paused_by is not None,
            verified_against_graph=run.targets.verified_against_graph,
        )

    def _text(self, run: _Run, step: _Step) -> str:
        values = {
            "from": run.targets.control_plane_version or "?",
            "to": run.target,
            "mce": run.targets.mce or "its MCE",
            "nodepool": step.nodepool or "",
            "steps": str(
                next((t.steps for t in run.targets.targets if t.version == run.target), 0)
                or len(_plan(run).steps)
            ),
        }
        return step.script.waiting_for.format_map(values)

    def _refusal(self, run: _Run, decision: str) -> UpgradeDecisionRefusedError:
        self._tick(run)
        step = run.steps[run.position]
        waiting = "resume" if run.paused_by else self._text(run, step)
        return UpgradeDecisionRefusedError(
            f"{decision} is not accepted now: the run is at {step.script.phase}, "
            f"waiting for {waiting}"
        )

    def _note(self, run: _Run, event: str, by: str | None, detail: str) -> None:
        run.log.append(LogLine(self._clock().isoformat(), event, by, detail))
        del run.log[:-LOG_LINES]

    def _check(self) -> None:
        if self.unavailable:
            raise WorkflowsUnavailableError("the orchestrator is unreachable (fake)")


def _newest(targets: UpgradeTargets, minor: str | None) -> str | None:
    return next((t.version for t in targets.targets if t.minor == minor), None)


def _last_of_pool(run: _Run, position: int) -> bool:
    following = run.steps[position + 1] if position + 1 < len(run.steps) else None
    return following is None or following.nodepool != run.steps[position].nodepool


def _steps_completed(run: _Run) -> int:
    """The plan's steps that ran to the end: the control plane's, then the workers'."""
    pools = {s.nodepool for s in run.steps if s.nodepool}
    workers = bool(pools) and pools <= set(run.done)
    return int(run.control_plane == run.target) + int(workers)


def _plan_step(step: _Step) -> int | None:
    return {"control_plane": 0, "each_nodepool": 1}.get(step.section)


def _plan(run: _Run) -> UpgradePlan:
    start = run.targets.control_plane_version or ""
    pools = tuple(dict.fromkeys(s.nodepool for s in run.steps if s.nodepool))
    steps = [PlanStep("control-plane", run.target, "target")]
    if pools:
        steps.append(PlanStep("workers", run.target, "final", pools))
    return UpgradePlan(start, run.target, 2, dict.fromkeys(pools, start), tuple(steps))


def demo_upgrades(script: UpgradeScript, *, clock: Clock = system_clock) -> FakeUpgradeWorkflow:
    """The fake with the fixture's demo runs started (``DAY1_FAKE_FLEET``, development only)."""
    fake = FakeUpgradeWorkflow(script, clock=clock)
    for demo in script.demo:
        request = UpgradeRequest(
            cluster=demo.cluster, requested_by=demo.by, target_version=demo.target
        )
        fake.seed(request, demo.decisions)
    return fake
