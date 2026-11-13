"""The upgrade routes' bodies (docs/notes/2026-11-13-upgrade-cluster-workflow-api.md, ADR-0055).

Apart from ``schemas.py`` so the upgrade's shapes read as one contract.
Request bodies forbid unknown fields; who asks is never one of them.
Responses pass the workflow's strings through.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from wingman_day1.application.upgrades import Decided, FleetUpgrade, StartUpgrade
from wingman_day1.domain.upgrades import (
    AgentVerdict,
    LogLine,
    PendingAction,
    PlanStep,
    TargetNodePool,
    UpgradePlan,
    UpgradeRun,
    UpgradeTarget,
    UpgradeTargets,
)

# ── Requests ─────────────────────────────────────────────────────────────────


class StartUpgradeIn(BaseModel):
    """``POST .../upgrade``: exactly one target; the rest only when the person chose it."""

    model_config = ConfigDict(extra="forbid")

    target_version: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=r"^\d+\.\d+\.\d+(-[a-z0-9_]+)?$"
    )
    target_minor: str | None = Field(default=None, pattern=r"^\d+\.\d+$")
    nodepool_order: list[str] | None = Field(default=None, min_length=1, max_length=100)
    max_unavailable: dict[str, StrictInt | StrictStr] | None = Field(default=None, max_length=100)
    """``{"<nodepool>": 2 | "33%"}``; the workflow judges the values."""
    workers_to_target: bool | None = None
    nodepool_mode: Literal["manual", "auto"] | None = None
    auto_approve: bool | None = None

    def choice(self) -> StartUpgrade:
        """For the use case."""
        return StartUpgrade(
            target_version=self.target_version,
            target_minor=self.target_minor,
            nodepool_order=tuple(self.nodepool_order) if self.nodepool_order else None,
            max_unavailable=self.max_unavailable,
            workers_to_target=self.workers_to_target,
            nodepool_mode=self.nodepool_mode,
            auto_approve=self.auto_approve,
        )


class UpgradeDecisionIn(BaseModel):
    """``POST .../upgrade-run/{decision}``: why (required for abort and approve-admin-ack)."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, min_length=1, max_length=1000)
    nodepool: str | None = Field(default=None, min_length=1, max_length=253)
    """``continue`` only: which NodePool rolls next (default: the next in the run's order)."""


# ── Targets ──────────────────────────────────────────────────────────────────


class UpgradeTargetOut(BaseModel):
    """One release the workflow offers."""

    version: str
    minor: str
    steps: int
    control_plane_steps: int
    newest_in_minor: bool
    must: bool

    @classmethod
    def of(cls, target: UpgradeTarget) -> UpgradeTargetOut:
        """From the domain."""
        return cls(
            version=target.version,
            minor=target.minor,
            steps=target.steps,
            control_plane_steps=target.control_plane_steps,
            newest_in_minor=target.newest_in_minor,
            must=target.must,
        )


class TargetNodePoolOut(BaseModel):
    """A NodePool of the file, as the workflow reads it."""

    name: str
    workertag: str | None
    upgrade_type: str | None
    zone: str | None
    replicas: int | None
    max_unavailable: str | None

    @classmethod
    def of(cls, pool: TargetNodePool) -> TargetNodePoolOut:
        """From the domain."""
        return cls(
            name=pool.name,
            workertag=pool.workertag,
            upgrade_type=pool.upgrade_type,
            zone=pool.zone,
            replicas=pool.replicas,
            max_unavailable=pool.max_unavailable,
        )


class UpgradeTargetsOut(BaseModel):
    """``GET .../upgrade-targets``; an empty ``targets`` is an answer."""

    cluster: str
    mce: str
    mce_version: str
    control_plane_version: str | None
    supported_minors: list[str]
    ladder_revision: str
    verified_against_graph: str | None
    targets: list[UpgradeTargetOut]
    nodepools: list[TargetNodePoolOut]
    nodepool_order: list[str]

    @classmethod
    def of(cls, found: UpgradeTargets) -> UpgradeTargetsOut:
        """From the domain."""
        return cls(
            cluster=found.cluster,
            mce=found.mce,
            mce_version=found.mce_version,
            control_plane_version=found.control_plane_version,
            supported_minors=list(found.supported_minors),
            ladder_revision=found.ladder_revision,
            verified_against_graph=found.verified_against_graph,
            targets=[UpgradeTargetOut.of(t) for t in found.targets],
            nodepools=[TargetNodePoolOut.of(p) for p in found.nodepools],
            nodepool_order=list(found.nodepool_order),
        )


# ── A run ────────────────────────────────────────────────────────────────────


class PlanStepOut(BaseModel):
    """One step of the plan; ``kind`` and ``reason`` are the workflow's words."""

    kind: str
    version: str
    reason: str
    nodepools: list[str]

    @classmethod
    def of(cls, step: PlanStep) -> PlanStepOut:
        """From the domain."""
        return cls(
            kind=step.kind, version=step.version, reason=step.reason, nodepools=list(step.nodepools)
        )


class UpgradePlanOut(BaseModel):
    """The path the workflow planned."""

    control_plane: str
    target: str
    max_worker_skew: int | None
    nodepools: dict[str, str]
    steps: list[PlanStepOut]

    @classmethod
    def of(cls, plan: UpgradePlan) -> UpgradePlanOut:
        """From the domain."""
        return cls(
            control_plane=plan.control_plane,
            target=plan.target,
            max_worker_skew=plan.max_worker_skew,
            nodepools=dict(plan.nodepools),
            steps=[PlanStepOut.of(s) for s in plan.steps],
        )


class PendingActionOut(BaseModel):
    """An action the upgrade agent proposed, flattened, and what a person decided."""

    action_id: str
    kind: str
    target: str
    args: dict[str, str]
    rationale: str
    decision: str
    decided_by: str | None
    executed: bool
    result: str | None

    @classmethod
    def of(cls, action: PendingAction) -> PendingActionOut:
        """From the domain."""
        return cls(
            action_id=action.action_id,
            kind=action.kind,
            target=action.target,
            args=dict(action.args),
            rationale=action.rationale,
            decision=action.decision,
            decided_by=action.decided_by,
            executed=action.executed,
            result=action.result,
        )


class AgentVerdictOut(BaseModel):
    """What the upgrade agent concluded."""

    diagnosis: str
    confidence: str
    verdict: str

    @classmethod
    def of(cls, verdict: AgentVerdict) -> AgentVerdictOut:
        """From the domain."""
        return cls(
            diagnosis=verdict.diagnosis, confidence=verdict.confidence, verdict=verdict.verdict
        )


class LogLineOut(BaseModel):
    """One line of the run's log."""

    at: str
    event: str
    by: str | None
    detail: str

    @classmethod
    def of(cls, line: LogLine) -> LogLineOut:
        """From the domain."""
        return cls(at=line.at, event=line.event, by=line.by, detail=line.detail)


class UpgradeRunOut(BaseModel):
    """``GET .../upgrade-run``: the run in the workflow's words; open while ``running``."""

    workflow_id: str
    cluster: str
    status: str
    phase: str | None
    waiting_for: str | None
    mce: str | None
    plan: UpgradePlanOut | None
    profile: str | None
    current_step: int | None
    current_nodepool: str | None
    nodepools_done: list[str]
    control_plane_version: str | None
    nodepool_versions: dict[str, str]
    max_unavailable: dict[str, str]
    paused: bool
    pending_actions: list[PendingActionOut]
    last_verdict: AgentVerdictOut | None
    verified_against_graph: str | None
    log: list[LogLineOut]
    outcome: str | None
    steps_completed: int | None
    error: str | None
    decisions: list[str] | None
    """The decisions the run accepts now, once the workflow reports them."""

    @classmethod
    def of(cls, run: UpgradeRun) -> UpgradeRunOut:
        """From the domain."""
        return cls(
            workflow_id=run.workflow_id,
            cluster=run.cluster,
            status=run.status,
            phase=run.phase,
            waiting_for=run.waiting_for,
            mce=run.mce,
            plan=UpgradePlanOut.of(run.plan) if run.plan else None,
            profile=run.profile,
            current_step=run.current_step,
            current_nodepool=run.current_nodepool,
            nodepools_done=list(run.nodepools_done),
            control_plane_version=run.control_plane_version,
            nodepool_versions=dict(run.nodepool_versions),
            max_unavailable=dict(run.max_unavailable),
            paused=run.paused,
            pending_actions=[PendingActionOut.of(a) for a in run.pending_actions],
            last_verdict=AgentVerdictOut.of(run.last_verdict) if run.last_verdict else None,
            verified_against_graph=run.verified_against_graph,
            log=[LogLineOut.of(line) for line in run.log],
            outcome=run.outcome,
            steps_completed=run.steps_completed,
            error=run.error,
            decisions=list(run.decisions) if run.decisions is not None else None,
        )


class UpgradeDecisionOut(BaseModel):
    """A decision the run took; ``run`` is ``null`` when it could not be read again."""

    workflow_id: str
    decision: str
    run: UpgradeRunOut | None

    @classmethod
    def of(cls, decided: Decided) -> UpgradeDecisionOut:
        """From the use case."""
        return cls(
            workflow_id=decided.workflow_id,
            decision=decided.decision,
            run=UpgradeRunOut.of(decided.run) if decided.run else None,
        )


# ── The fleet's list ─────────────────────────────────────────────────────────


class FleetUpgradeOut(BaseModel):
    """One cluster's newest upgrade run, for the clusters list's "Upgrading" rows."""

    workflow_id: str
    cluster: str
    """The cluster file's stem."""
    site: str | None
    mce: str | None
    """Where day1 has the file; ``null`` when it has none (or several)."""
    status: str
    started_at: str | None
    """When the upgrade's first segment started."""
    closed_at: str | None
    phase: str | None
    """The workflow's own word; ``null`` when closed, or not read (only the first rows are)."""
    waiting_for: str | None
    paused: bool
    outcome: str | None

    @classmethod
    def of(cls, upgrade: FleetUpgrade) -> FleetUpgradeOut:
        """From the use case: the run's own read where made, else the list's entry."""
        row, run, ref = upgrade.row, upgrade.run, upgrade.ref
        return cls(
            workflow_id=row.workflow_id,
            cluster=row.cluster,
            site=ref.site if ref else None,
            mce=ref.mce if ref else None,
            status=run.status if run else row.status,
            started_at=row.started_at.isoformat() if row.started_at else None,
            closed_at=row.closed_at.isoformat() if row.closed_at else None,
            phase=run.phase if run else None,
            waiting_for=run.waiting_for if run else None,
            paused=run.paused if run else False,
            outcome=run.outcome if run else None,
        )


class FleetUpgradesOut(BaseModel):
    """``GET /api/day1/upgrades``: every cluster's newest upgrade run, open ones first."""

    runs: list[FleetUpgradeOut]
