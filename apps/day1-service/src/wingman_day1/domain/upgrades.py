"""A hosted cluster's upgrade through the platform's upgrade-cluster workflow (ADR-0055).

The workflow owns the upgrade: it plans the path along the day1 repo's
ladder, pre-flights, waits for an approval, and then commits ``mastertag``,
each NodePool's ``workertag`` and, on an abort, ``pausedUntil`` to day1
``main`` itself. Wingman starts a run, shows it and passes on a person's
decisions (``docs/notes/2026-11-13-upgrade-cluster-workflow-api.md``). Only
data crosses back: these types hold the workflow's strings as it gives them.
There is no phase list: a phase the workflow adds is shown humanized.

While upgrades are on, those keys are the workflow's (ADR-0012's key
ownership, amended): :func:`version_problems` is the one rule that refuses an
edit changing them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

UPGRADE_WORKFLOW_PREFIX: Final = "upgrade-cluster-"
"""A cluster's upgrade run is ``upgrade-cluster-<file stem>``; the next upgrade reuses it."""
VERSIONS_BY_UPGRADE: Final = "Versions change through Upgrade on the cluster page"


def upgrade_workflow_id(stem: str) -> str:
    """The id of the upgrade run for the cluster file ``<stem>.yaml``."""
    return f"{UPGRADE_WORKFLOW_PREFIX}{stem}"


class UpgradeDecision(StrEnum):
    """What a person may decide on a run; the run's validators judge whether it is accepted."""

    APPROVE = "approve"
    APPROVE_ADMIN_ACK = "approve-admin-ack"
    CONTINUE = "continue"
    CONFIRM_DAY2 = "confirm-day2"
    PAUSE = "pause"
    RESUME = "resume"
    ABORT = "abort"
    RETRY = "retry"

    @property
    def needs_reason(self) -> bool:
        """The workflow refuses these without a reason."""
        return self in (UpgradeDecision.ABORT, UpgradeDecision.APPROVE_ADMIN_ACK)

    @property
    def takes_reason(self) -> bool:
        """``continue`` takes a NodePool, not a reason (its body forbids one)."""
        return self is not UpgradeDecision.CONTINUE


# ── The targets: the workflow's answer to "what can this cluster go to" ──────


@dataclass(frozen=True, slots=True)
class UpgradeTarget:
    """One release the cluster can be upgraded to, as the workflow offers it."""

    version: str
    minor: str
    steps: int
    """How many steps the plan to it has, control plane and workers."""
    control_plane_steps: int
    newest_in_minor: bool
    must: bool = False


@dataclass(frozen=True, slots=True)
class TargetNodePool:
    """A NodePool of the cluster file, as the workflow reads it."""

    name: str
    workertag: str | None = None
    upgrade_type: str | None = None
    zone: str | None = None
    replicas: int | None = None
    max_unavailable: str | None = None


@dataclass(frozen=True, slots=True)
class UpgradeTargets:
    """The targets of one cluster; an empty ``targets`` is an answer, not an error."""

    cluster: str
    mce: str
    mce_version: str
    control_plane_version: str | None
    """The file's mastertag, bare."""
    supported_minors: tuple[str, ...]
    ladder_revision: str
    verified_against_graph: str | None
    targets: tuple[UpgradeTarget, ...] = ()
    nodepools: tuple[TargetNodePool, ...] = ()
    nodepool_order: tuple[str, ...] = ()


# ── A start ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class UpgradeRequest:
    """A start: the cluster, who asked, one target, and what the person chose to set.

    ``None`` is "not sent": the workflow's default applies.
    """

    cluster: str
    requested_by: str
    target_version: str | None = None
    target_minor: str | None = None
    nodepool_order: tuple[str, ...] | None = None
    max_unavailable: Mapping[str, int | str] | None = None
    workers_to_target: bool | None = None
    nodepool_mode: str | None = None
    auto_approve: bool | None = None

    @property
    def target(self) -> str:
        """The target as the person chose it, for logs."""
        return self.target_version or self.target_minor or ""


# ── A run ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PlanStep:
    """One step of the workflow's plan: the control plane, or NodePools, to ``version``."""

    kind: str
    version: str
    reason: str
    nodepools: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UpgradePlan:
    """The path the workflow planned."""

    control_plane: str
    target: str
    max_worker_skew: int | None
    nodepools: Mapping[str, str]
    steps: tuple[PlanStep, ...]


@dataclass(frozen=True, slots=True)
class PendingAction:
    """An action the upgrade agent proposed, and what a person decided."""

    action_id: str
    kind: str
    target: str
    args: Mapping[str, str]
    rationale: str
    decision: str
    decided_by: str | None
    executed: bool
    result: str | None


@dataclass(frozen=True, slots=True)
class AgentVerdict:
    """What the upgrade agent concluded at a failed gate."""

    diagnosis: str
    confidence: str
    verdict: str


@dataclass(frozen=True, slots=True)
class LogLine:
    """One line of the run's log."""

    at: str
    event: str
    by: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class UpgradeRun:
    """An upgrade-cluster run, as the orchestrator reports it, in the workflow's words."""

    workflow_id: str
    status: str
    """The orchestrator's status, lowercase: ``running`` (the run is open), ``completed``, ..."""
    phase: str | None = None
    waiting_for: str | None = None
    mce: str | None = None
    plan: UpgradePlan | None = None
    profile: str | None = None
    current_step: int | None = None
    current_nodepool: str | None = None
    nodepools_done: tuple[str, ...] = ()
    control_plane_version: str | None = None
    nodepool_versions: Mapping[str, str] = field(default_factory=dict)
    max_unavailable: Mapping[str, str] = field(default_factory=dict)
    paused: bool = False
    pending_actions: tuple[PendingAction, ...] = ()
    last_verdict: AgentVerdict | None = None
    verified_against_graph: str | None = None
    log: tuple[LogLine, ...] = ()
    outcome: str | None = None
    """Once completed: ``done``, ``cancelled`` (aborted before approval) or ``aborted``."""
    steps_completed: int | None = None
    error: str | None = None
    decisions: tuple[str, ...] | None = None
    """The decisions the run accepts now, once the workflow reports them; ``None`` until then."""

    @property
    def cluster(self) -> str:
        """The cluster file's stem the run upgrades."""
        return self.workflow_id.removeprefix(UPGRADE_WORKFLOW_PREFIX)


# ── Who owns the version keys while upgrades are on (ADR-0055) ───────────────


def version_problems(old: Mapping[str, object], new: Mapping[str, object]) -> list[str]:
    """Why an edit from ``old`` to ``new`` (parsed values) touches what the workflow owns.

    ``mastertag``, the top-level ``workertag`` and each NodePool's
    ``workertag`` must stay as they are; ``pausedUntil`` may be removed but
    not added or changed. A NodePool new in the edit may carry a
    ``workertag`` only equal to what it would follow without one; removing a
    NodePool is not a version change. Empty when the edit leaves them alone.
    """
    problems = [
        f"{key}: {VERSIONS_BY_UPGRADE}"
        for key in ("mastertag", "workertag")
        if old.get(key) != new.get(key)
    ]
    if "pausedUntil" in new and new.get("pausedUntil") != old.get("pausedUntil"):
        problems.append(
            f"pausedUntil: only an aborted upgrade sets it, and an edit may only remove it. "
            f"{VERSIONS_BY_UPGRADE}"
        )
    before = _workertags(old.get("nodepool"))
    follows = new.get("workertag") or new.get("mastertag")
    for name, tag in _workertags(new.get("nodepool")).items():
        if name in before:
            changed = before[name] != tag
        else:
            changed = tag is not None and _bare(tag) != _bare(follows)
        if changed:
            problems.append(f"nodepool {name} workertag: {VERSIONS_BY_UPGRADE}")
    return problems


def _workertags(pools: object) -> dict[str, object]:
    """Each NodePool's ``workertag`` (``None``: none), by its name, else its InfraEnv."""
    tags: dict[str, object] = {}
    if not isinstance(pools, Sequence) or isinstance(pools, str):
        return tags
    for index, pool in enumerate(pools):
        if not isinstance(pool, Mapping):
            continue
        key = pool.get("name") or pool.get("infraEnvName") or f"#{index}"
        tags.setdefault(str(key), pool.get("workertag"))
    return tags


def _bare(version: object) -> str | None:
    """``4.18.22-x86_64`` and ``4.18.22`` are the same release."""
    return None if version is None else str(version).removesuffix("-x86_64")
