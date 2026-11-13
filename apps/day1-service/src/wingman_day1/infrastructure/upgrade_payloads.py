"""The upgrade-cluster workflow's JSON, read into ``wingman_day1.domain.upgrades`` (ADR-0055).

Apart from the HTTP adapter so each reads as one thing. The run's id and
status, and the targets' cluster, must be there; every other field is
optional and read leniently: a field of the wrong type is left out rather
than failing the whole read, since the workflow adds and moves fields (its
phases, its progress). Strings are kept as the workflow wrote them.
Malformed required fields raise ``TypeError``/``KeyError``/``ValueError``,
which the adapter turns into ``WorkflowsUnavailableError``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from wingman_day1.domain.servers import run_status
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
from wingman_day1.infrastructure.http import JSON, required_text

MAX_LOG: Final = 50
"""The workflow keeps its last 20 lines; more than this is not shown."""


def _text(raw: Mapping[str, JSON], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) and value else None


def _int(raw: Mapping[str, JSON], key: str) -> int | None:
    value = raw.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _object(value: JSON) -> dict[str, JSON]:
    return value if isinstance(value, dict) else {}


def _texts(value: JSON) -> tuple[str, ...]:
    return tuple(v for v in value if isinstance(v, str)) if isinstance(value, list) else ()


def _text_map(value: JSON) -> dict[str, str]:
    """``{name: text}``; numbers (a ``max_unavailable`` of 2) are kept as text."""
    if not isinstance(value, dict):
        return {}
    return {
        str(k): str(v)
        for k, v in value.items()
        if isinstance(v, str | int) and not isinstance(v, bool)
    }


# ── Targets ──────────────────────────────────────────────────────────────────


def upgrade_targets(raw: JSON) -> UpgradeTargets:
    """``GET /workflows/cluster-upgrade/upgrade-targets``'s 200."""
    if not isinstance(raw, dict):
        raise TypeError("the targets are not an object")
    return UpgradeTargets(
        cluster=required_text(raw, "cluster"),
        mce=_text(raw, "mce_cluster") or "",
        mce_version=_text(raw, "mce_version") or "",
        control_plane_version=_text(raw, "control_plane_version"),
        supported_minors=_texts(raw.get("supported_minors")),
        ladder_revision=_text(raw, "ladder_revision") or "",
        verified_against_graph=_text(raw, "verified_against_graph"),
        targets=tuple(
            t for t in (_target(item) for item in _list(raw.get("targets"))) if t is not None
        ),
        nodepools=tuple(
            p for p in (_target_pool(item) for item in _list(raw.get("nodepools"))) if p
        ),
        nodepool_order=_texts(raw.get("nodepool_order")),
    )


def _list(value: JSON) -> list[JSON]:
    return value if isinstance(value, list) else []


def _target(raw: JSON) -> UpgradeTarget | None:
    if not isinstance(raw, dict) or not _text(raw, "version"):
        return None
    return UpgradeTarget(
        version=str(raw["version"]),
        minor=_text(raw, "minor") or "",
        steps=_int(raw, "steps") or 0,
        control_plane_steps=_int(raw, "control_plane_steps") or 0,
        newest_in_minor=raw.get("newest_in_minor") is True,
        must=raw.get("must") is True,
    )


def _target_pool(raw: JSON) -> TargetNodePool | None:
    if not isinstance(raw, dict) or not _text(raw, "name"):
        return None
    max_unavailable = raw.get("max_unavailable")
    return TargetNodePool(
        name=str(raw["name"]),
        workertag=_text(raw, "workertag"),
        upgrade_type=_text(raw, "upgrade_type"),
        zone=_text(raw, "zone"),
        replicas=_int(raw, "replicas"),
        max_unavailable=(
            str(max_unavailable)
            if isinstance(max_unavailable, str | int) and not isinstance(max_unavailable, bool)
            else None
        ),
    )


# ── A run ────────────────────────────────────────────────────────────────────


def upgrade_run(raw: JSON) -> UpgradeRun:
    """``GET /workflows/runs/{id}`` for an upgrade-cluster run.

    While it runs (and after a failure), ``progress`` is the workflow's;
    once completed, ``result`` holds the outcome, the plan and the final
    versions.
    """
    if not isinstance(raw, dict):
        raise TypeError("the run is not an object")
    workflow_id, status = raw["workflow_id"], raw["status"]
    if not (isinstance(workflow_id, str) and workflow_id and isinstance(status, str)):
        raise ValueError("the run has no workflow_id or status")
    progress, result = _object(raw.get("progress")), _object(raw.get("result"))
    source = progress or result
    decisions = progress.get("decisions")
    return UpgradeRun(
        workflow_id=workflow_id,
        status=run_status(status),
        phase=_text(progress, "phase"),
        waiting_for=_text(progress, "waiting_for"),
        mce=_text(source, "mce_cluster"),
        plan=_plan(source.get("plan")),
        profile=_text(progress, "profile"),
        current_step=_int(progress, "current_step"),
        current_nodepool=_text(progress, "current_nodepool"),
        nodepools_done=_texts(progress.get("nodepools_done")),
        control_plane_version=_text(source, "control_plane_version"),
        nodepool_versions=_text_map(source.get("nodepool_versions")),
        max_unavailable=_text_map(progress.get("max_unavailable")),
        paused=progress.get("paused") is True,
        pending_actions=tuple(
            a for a in (_pending(item) for item in _list(progress.get("pending_actions"))) if a
        ),
        last_verdict=_verdict(progress.get("last_verdict")),
        verified_against_graph=_text(progress, "verified_against_graph"),
        log=tuple(line for line in (_log_line(item) for item in _list(source.get("log"))) if line)[
            -MAX_LOG:
        ],
        outcome=_text(result, "outcome"),
        steps_completed=_int(result, "steps_completed"),
        error=_text(raw, "error"),
        decisions=_texts(decisions) if isinstance(decisions, list) else None,
    )


def _plan(raw: JSON) -> UpgradePlan | None:
    if not isinstance(raw, dict) or not _text(raw, "control_plane") or not _text(raw, "target"):
        return None
    return UpgradePlan(
        control_plane=str(raw["control_plane"]),
        target=str(raw["target"]),
        max_worker_skew=_int(raw, "max_worker_skew"),
        nodepools=_text_map(raw.get("nodepools")),
        steps=tuple(s for s in (_step(item) for item in _list(raw.get("steps"))) if s),
    )


def _step(raw: JSON) -> PlanStep | None:
    if not isinstance(raw, dict) or not _text(raw, "kind") or not _text(raw, "version"):
        return None
    return PlanStep(
        kind=str(raw["kind"]),
        version=str(raw["version"]),
        reason=_text(raw, "reason") or "",
        nodepools=_texts(raw.get("nodepools")),
    )


def _pending(raw: JSON) -> PendingAction | None:
    if not isinstance(raw, dict):
        return None
    action = _object(raw.get("action"))
    action_id = _text(action, "action_id")
    if action_id is None:
        return None
    return PendingAction(
        action_id=action_id,
        kind=_text(action, "kind") or "",
        target=_text(action, "target") or "",
        args=_text_map(action.get("args")),
        rationale=_text(action, "rationale") or "",
        decision=_text(raw, "decision") or "pending",
        decided_by=_text(raw, "decided_by"),
        executed=raw.get("executed") is True,
        result=_text(raw, "result"),
    )


def _verdict(raw: JSON) -> AgentVerdict | None:
    if not isinstance(raw, dict) or not _text(raw, "diagnosis"):
        return None
    return AgentVerdict(
        diagnosis=str(raw["diagnosis"]),
        confidence=_text(raw, "confidence") or "",
        verdict=_text(raw, "verdict") or "",
    )


def _log_line(raw: JSON) -> LogLine | None:
    if not isinstance(raw, dict) or not _text(raw, "event"):
        return None
    return LogLine(
        at=_text(raw, "at") or "",
        event=str(raw["event"]),
        by=_text(raw, "by"),
        detail=_text(raw, "detail") or "",
    )
