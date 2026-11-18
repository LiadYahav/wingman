"""The update-nodepool workflow's run JSON, read into ``wingman_day1.domain.scale`` (ADR-0062).

``GET /workflows/runs/{id}`` answers ``{workflow_id, workflow_type, status,
progress?, result?, error?}``: ``progress`` is the run's ``progress`` query
(``phase``, ``direction``, ``child_workflow_id``) while it runs and after a
failure, ``result`` the ``UpdateNodePoolResult`` once completed, with its
child's ``NodePoolScaleResult`` in ``scale`` (``infra_env_kind`` only on a
run recorded by kind before 2026-11-18). The id and status must be
there; everything else is read leniently, since the workflow's branch can
still change: an unknown field is ignored, a field of the wrong type is left
out, and strings are kept as the workflow wrote them. Malformed required
fields raise ``TypeError``/``KeyError``/``ValueError``, which the adapter
turns into ``WorkflowsUnavailableError``.
"""

from __future__ import annotations

from collections.abc import Mapping

from wingman_day1.domain.scale import (
    ChosenServer,
    LiveReplicas,
    NodePoolChange,
    ScaleChild,
    ScaleResult,
    ScaleRun,
)
from wingman_day1.domain.servers import run_status
from wingman_day1.infrastructure.http import JSON, required_text


def _text(raw: Mapping[str, JSON], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) and value else None


def _int(raw: Mapping[str, JSON], key: str) -> int | None:
    value = raw.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _object(value: JSON) -> dict[str, JSON]:
    return value if isinstance(value, dict) else {}


def _objects(value: JSON) -> list[dict[str, JSON]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _texts(value: JSON) -> tuple[str, ...]:
    return tuple(v for v in value if isinstance(v, str) and v) if isinstance(value, list) else ()


def scale_run(raw: JSON) -> ScaleRun:
    """One run of update-nodepool; its child is read separately (``with_child``)."""
    if not isinstance(raw, dict):
        raise TypeError("the run is not an object")
    progress = _object(raw.get("progress"))
    result = raw.get("result")
    return ScaleRun(
        workflow_id=required_text(raw, "workflow_id"),
        status=run_status(required_text(raw, "status")),
        phase=_text(progress, "phase"),
        direction=_text(progress, "direction") or _text(_object(result), "direction"),
        child=ScaleChild(child) if (child := _text(progress, "child_workflow_id")) else None,
        result=scale_result(result) if isinstance(result, dict) else None,
        error=_text(raw, "error"),
    )


def child_run(workflow_id: str, raw: JSON) -> ScaleChild:
    """The scale-up-nodepool or scale-down-nodepool run, as far as it reads."""
    found = _object(raw)
    status = _text(found, "status")
    return ScaleChild(
        workflow_id=workflow_id,
        status=run_status(status) if status else None,
        phase=_text(_object(found.get("progress")), "phase"),
        error=_text(found, "error"),
    )


def scale_result(raw: Mapping[str, JSON]) -> ScaleResult:
    """``UpdateNodePoolResult``, with its child's result in ``scale`` flattened in."""
    scale = _object(raw.get("scale"))
    return ScaleResult(
        direction=_text(raw, "direction") or "none",
        infra_env_kind=_text(raw, "infra_env_kind"),
        nodepool=_text(raw, "nodepool"),
        day1_path=_text(raw, "day1_path"),
        total_before=_int(raw, "total_before"),
        total_after=_int(raw, "total_after"),
        nodepools=tuple(
            NodePoolChange(
                name=str(item["name"]),
                infra_env=_text(item, "infra_env"),
                before=_int(item, "before"),
                after=_int(item, "after"),
                scale_down_policy=_text(item, "scale_down_policy"),
            )
            for item in _objects(raw.get("nodepools"))
            if _text(item, "name")
        ),
        child_workflow_id=_text(raw, "child_workflow_id"),
        revision=_text(scale, "revision"),
        committed=scale["committed"] if isinstance(scale.get("committed"), bool) else None,
        live=tuple(
            LiveReplicas(
                name=str(item["name"]),
                replicas=_int(item, "replicas"),
                ready_replicas=_int(item, "ready_replicas"),
            )
            for item in _objects(scale.get("nodepools"))
            if _text(item, "name")
        ),
        chosen=tuple(
            ChosenServer(
                nodepool=str(item["nodepool"]),
                machine=str(item["machine"]),
                node=_text(item, "node"),
                policy=_text(item, "policy") or "",
                reason=_text(item, "reason") or "",
                server=_text(item, "server"),
            )
            for item in _objects(scale.get("chosen"))
            if _text(item, "nodepool") and _text(item, "machine")
        ),
        deleting=_texts(scale.get("deleting")),
        ignored=_texts(raw.get("ignored")),
    )
