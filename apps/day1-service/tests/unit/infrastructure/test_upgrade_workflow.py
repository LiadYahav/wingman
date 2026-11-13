"""HttpUpgradeWorkflow against the orchestrator's answers (MockTransport, ADR-0055).

A start and a decision are writes: sent once, never retried (ADR-0006).
Refused before it left is "nothing sent"; sent and unanswered may have
happened. The run's validators judge every decision, and a refusal keeps
their words. The bodies are checked against the orchestrator's own OpenAPI.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import (
    AmbiguousDecisionError,
    AmbiguousStartError,
    InvalidInputError,
    ResourceNotFoundError,
    UpgradeAlreadyRunningError,
    UpgradeDecisionRefusedError,
    UpgradeRefusedError,
    UpgradeTargetsRefusedError,
    WorkflowRefusedError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.upgrades import UpgradeDecision, UpgradeRequest, upgrade_workflow_id
from wingman_day1.infrastructure.upgrade_workflow import HttpUpgradeWorkflow

CLUSTER = "ocp4-prod-lark-site1"
WORKFLOW_ID = upgrade_workflow_id(CLUSTER)
UPGRADE = "/workflows/cluster-upgrade/upgrade-cluster"
TARGETS = "/workflows/cluster-upgrade/upgrade-targets"
OPENAPI = (
    Path(__file__).resolve().parents[5] / "docs/ecosystem/notes/workflows-orchestrator-openapi.json"
)
REQUEST = UpgradeRequest(cluster=CLUSTER, requested_by="alice", target_version="4.18.56")
WAITING = "approve: 4.18.22 → 4.18.56 in 2 steps (control plane, then 2 NodePools)"
REFUSAL = (
    "continue is not accepted: the run is at awaiting-approval, waiting for " + WAITING + " " * 3
) * 3

Handler = Callable[[httpx.Request], httpx.Response]


def make(
    handler: Handler, *, metrics: WingmanMetrics | None = None
) -> tuple[HttpUpgradeWorkflow, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    workflow = HttpUpgradeWorkflow(
        base_url="http://workflows-orchestrator-api.redbull-workflows.svc:8080/",
        timeout_seconds=2.0,
        targets_timeout_seconds=65.0,
        metrics=metrics,
        transport=httpx.MockTransport(record),
        timer=iter(range(1000)).__next__,
    )
    return workflow, requests


def answer(status: int, body: object) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


def failing(error: type[httpx.TransportError]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error("boom", request=request)

    return handler


def body(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)


# ── Start ────────────────────────────────────────────────────────────────────


async def test_a_start_sends_the_cluster_who_asked_and_only_what_was_chosen() -> None:
    workflow, requests = make(answer(202, {"workflow_id": WORKFLOW_ID, "run_id": "r1"}))
    chosen = UpgradeRequest(
        cluster=CLUSTER,
        requested_by="alice",
        target_minor="4.18",
        nodepool_order=("b", "a"),
        max_unavailable={"a": 2, "b": "33%"},
        workers_to_target=False,
    )
    run = await workflow.start(chosen)
    assert (run.workflow_id, run.status, run.cluster) == (WORKFLOW_ID, "running", CLUSTER)
    [sent] = requests
    assert (sent.method, sent.url.path) == ("POST", UPGRADE)
    assert body(sent) == {
        "cluster": CLUSTER,
        "requested_by": "alice",
        "target_minor": "4.18",
        "nodepool_order": ["b", "a"],
        "max_unavailable": {"a": 2, "b": "33%"},
        "workers_to_target": False,
    }


async def test_an_open_run_is_a_conflict_sent_once() -> None:
    detail = {"detail": f"{CLUSTER} already has an upgrade run: {WORKFLOW_ID}"}
    workflow, requests = make(answer(409, detail))
    with pytest.raises(UpgradeAlreadyRunningError, match="already has an upgrade run"):
        await workflow.start(REQUEST)
    assert len(requests) == 1


async def test_a_refused_body_lists_the_orchestrators_findings() -> None:
    findings = {"detail": [{"loc": ["body", "max_unavailable"], "msg": "NodePool a: 0 is not"}]}
    workflow, _ = make(answer(422, findings))
    with pytest.raises(UpgradeRefusedError) as refused:
        await workflow.start(REQUEST)
    assert isinstance(refused.value, InvalidInputError)
    assert refused.value.problems == ("max_unavailable: NodePool a: 0 is not",)


async def test_another_4xx_is_a_refusal_and_a_5xx_is_unavailable() -> None:
    for status, error in ((400, WorkflowRefusedError), (502, WorkflowsUnavailableError)):
        workflow, _ = make(answer(status, {"detail": "no"}))
        with pytest.raises(error):
            await workflow.start(REQUEST)


async def test_a_gateway_timeout_a_lost_answer_or_an_unreadable_202_is_ambiguous() -> None:
    for handler in (
        answer(504, {}),
        failing(httpx.ReadTimeout),
        answer(202, {"run_id": "no workflow id"}),
    ):
        workflow, requests = make(handler)
        with pytest.raises(AmbiguousStartError, match="upgrade run"):
            await workflow.start(REQUEST)
        assert len(requests) == 1, "never retried"


async def test_an_unreachable_orchestrator_started_nothing() -> None:
    workflow, _ = make(failing(httpx.ConnectError))
    with pytest.raises(WorkflowsUnavailableError, match="nothing was started"):
        await workflow.start(REQUEST)


# ── Decisions ────────────────────────────────────────────────────────────────


async def test_a_decision_posts_who_decided_and_only_the_fields_it_takes() -> None:
    workflow, requests = make(answer(200, {"workflow_id": WORKFLOW_ID, "decision": "x"}))
    await workflow.decide(WORKFLOW_ID, UpgradeDecision.APPROVE, by="alice", reason="looks right")
    await workflow.decide(
        WORKFLOW_ID, UpgradeDecision.CONTINUE, by="alice", reason="dropped", nodepool="pool-b"
    )
    await workflow.decide(WORKFLOW_ID, UpgradeDecision.PAUSE, by="alice", nodepool="dropped")
    await workflow.decide_action(WORKFLOW_ID, "act-1", approve=False, by="alice")
    assert [(r.url.path, body(r)) for r in requests] == [
        (f"{UPGRADE}/{WORKFLOW_ID}/approve", {"by": "alice", "reason": "looks right"}),
        (f"{UPGRADE}/{WORKFLOW_ID}/continue", {"by": "alice", "nodepool": "pool-b"}),
        (f"{UPGRADE}/{WORKFLOW_ID}/pause", {"by": "alice"}),
        (f"{UPGRADE}/{WORKFLOW_ID}/actions/act-1/reject", {"by": "alice"}),
    ]


async def test_a_refused_decision_keeps_the_runs_words_whole() -> None:
    workflow, _ = make(answer(409, {"detail": REFUSAL}))
    with pytest.raises(UpgradeDecisionRefusedError) as refused:
        await workflow.decide(WORKFLOW_ID, UpgradeDecision.CONTINUE, by="alice")
    assert str(refused.value) == REFUSAL.strip()


async def test_no_running_run_is_not_found_and_a_failed_update_is_unavailable() -> None:
    workflow, _ = make(answer(404, {"detail": f"no running upgrade-cluster run {WORKFLOW_ID}"}))
    with pytest.raises(ResourceNotFoundError, match="no running"):
        await workflow.decide(WORKFLOW_ID, UpgradeDecision.RETRY, by="alice")
    workflow, _ = make(answer(500, {"detail": "the retry update failed"}))
    with pytest.raises(WorkflowsUnavailableError, match="answered 500"):
        await workflow.decide(WORKFLOW_ID, UpgradeDecision.RETRY, by="alice")


async def test_an_unanswered_decision_is_ambiguous_and_an_unsent_one_is_not() -> None:
    for handler in (answer(504, {"detail": "no answer in 15s"}), failing(httpx.ReadError)):
        workflow, requests = make(handler)
        with pytest.raises(AmbiguousDecisionError, match="may have been taken"):
            await workflow.decide(WORKFLOW_ID, UpgradeDecision.ABORT, by="alice", reason="r")
        assert len(requests) == 1, "never retried"
    workflow, _ = make(failing(httpx.ConnectError))
    with pytest.raises(WorkflowsUnavailableError, match="nothing was sent"):
        await workflow.decide(WORKFLOW_ID, UpgradeDecision.ABORT, by="alice", reason="r")


# ── Targets ──────────────────────────────────────────────────────────────────

TARGETS_ANSWER = {
    "cluster": CLUSTER,
    "mce_cluster": "ocp4-prod-mce-site1-a",
    "mce_version": "2.8.2",
    "control_plane_version": "4.18.22",
    "supported_minors": ["4.18", "4.17"],
    "ladder_revision": "3f2a9c1",
    "verified_against_graph": "2026-10-31",
    "targets": [
        {
            "version": "4.18.56",
            "minor": "4.18",
            "steps": 2,
            "control_plane_steps": 1,
            "newest_in_minor": True,
            "must": True,
        },
        {"minor": "4.18"},
    ],
    "nodepools": [
        {"name": "pool-a", "workertag": None, "upgrade_type": "InPlace", "max_unavailable": 2},
        {"name": "pool-b", "zone": "b", "replicas": 3, "max_unavailable": "33%"},
    ],
    "nodepool_order": ["pool-a", "pool-b"],
}


async def test_targets_are_read_with_their_own_timeout_and_passed_through() -> None:
    workflow, requests = make(answer(200, TARGETS_ANSWER))
    found = await workflow.targets(CLUSTER)
    [sent] = requests
    assert (sent.url.path, sent.url.params["cluster"]) == (TARGETS, CLUSTER)
    assert sent.extensions["timeout"]["read"] == 65.0
    assert (found.mce, found.control_plane_version, found.ladder_revision) == (
        "ocp4-prod-mce-site1-a",
        "4.18.22",
        "3f2a9c1",
    )
    assert [t.version for t in found.targets] == ["4.18.56"], "a target without a version is left"
    assert [(p.name, p.max_unavailable) for p in found.nodepools] == [
        ("pool-a", "2"),
        ("pool-b", "33%"),
    ]
    assert found.nodepool_order == ("pool-a", "pool-b")


async def test_an_empty_target_list_is_an_answer() -> None:
    workflow, _ = make(answer(200, {**TARGETS_ANSWER, "targets": []}))
    assert (await workflow.targets(CLUSTER)).targets == ()


async def test_targets_refusals_carry_the_workflows_words() -> None:
    cases: list[tuple[int, type[Exception], str]] = [
        (404, ResourceNotFoundError, "day1 has no"),
        (409, UpgradeTargetsRefusedError, "cannot use"),
        (504, WorkflowsUnavailableError, "is the upgrade-gitops limb running"),
    ]
    for status, error, words in cases:
        detail = {"detail": "no answer in 60s: is the upgrade-gitops limb running?"}
        workflow, _ = make(answer(status, detail))
        with pytest.raises(error, match=words):
            await workflow.targets(CLUSTER)


async def test_targets_that_time_out_or_are_malformed_are_unavailable() -> None:
    for handler in (failing(httpx.ReadTimeout), answer(200, ["not", "an", "object"])):
        workflow, _ = make(handler)
        with pytest.raises(WorkflowsUnavailableError):
            await workflow.targets(CLUSTER)


# ── The run ──────────────────────────────────────────────────────────────────

PROGRESS = {
    "phase": "needs-human",
    "waiting_for": "retry or abort: the gate failed",
    "mce_cluster": "ocp4-prod-mce-site1-a",
    "plan": {
        "control_plane": "4.18.22",
        "target": "4.18.56",
        "max_worker_skew": 2,
        "nodepools": {"pool-a": "4.18.22"},
        "steps": [
            {"kind": "control-plane", "version": "4.18.56", "reason": "target", "nodepools": []},
            {"kind": "workers", "version": "4.18.56", "reason": "final", "nodepools": ["pool-a"]},
        ],
        "pinned": {"4.18.56": {"release": "quay.io/x@sha256:1"}},
    },
    "profile": "generic",
    "current_step": 1,
    "current_nodepool": "pool-a",
    "nodepools_done": [],
    "control_plane_version": "4.18.56",
    "nodepool_versions": {"pool-a": "4.18.22"},
    "max_unavailable": {"pool-a": "2"},
    "paused": False,
    "pending_actions": [
        {
            "action": {
                "action_id": "act-1",
                "kind": "delete-pod",
                "target": "ns/pod",
                "args": {"grace": "0"},
                "rationale": "stuck",
            },
            "decision": "pending",
        },
        {"action": {"kind": "no id"}},
    ],
    "last_verdict": {
        "diagnosis": "a PDB blocks the drain",
        "confidence": "observed",
        "verdict": "needs_human",
    },
    "verified_against_graph": "2026-10-31",
    "log": [{"at": "2026-11-13T10:00:00Z", "event": "approved", "by": "alice"}, {"by": "x"}],
    "decisions": ["retry", "abort"],
    "a_field_from_tomorrow": {"x": 1},
}


async def test_a_running_run_is_read_in_the_workflows_words() -> None:
    raw = {"workflow_id": WORKFLOW_ID, "status": "RUNNING", "progress": PROGRESS}
    workflow, requests = make(answer(200, raw))
    run = await workflow.run(WORKFLOW_ID)
    assert run is not None
    assert requests[0].url.path == f"/workflows/runs/{WORKFLOW_ID}"
    assert (run.status, run.phase, run.waiting_for, run.mce) == (
        "running",
        "needs-human",
        "retry or abort: the gate failed",
        "ocp4-prod-mce-site1-a",
    )
    assert run.plan is not None
    assert [(s.kind, s.version, s.nodepools) for s in run.plan.steps] == [
        ("control-plane", "4.18.56", ()),
        ("workers", "4.18.56", ("pool-a",)),
    ]
    assert (run.current_step, run.current_nodepool, run.max_unavailable) == (
        1,
        "pool-a",
        {"pool-a": "2"},
    )
    assert [(a.action_id, a.args, a.decision) for a in run.pending_actions] == [
        ("act-1", {"grace": "0"}, "pending")
    ]
    assert run.last_verdict is not None and run.last_verdict.verdict == "needs_human"
    assert [(line.event, line.by) for line in run.log] == [("approved", "alice")]
    assert (run.decisions, run.outcome) == (("retry", "abort"), None)


async def test_a_completed_run_takes_its_outcome_plan_and_versions_from_its_result() -> None:
    result = {
        "outcome": "aborted",
        "mce_cluster": "ocp4-prod-mce-site1-a",
        "cluster": CLUSTER,
        "plan": PROGRESS["plan"],
        "steps_completed": 1,
        "control_plane_version": "4.18.56",
        "nodepool_versions": {"pool-a": "4.18.22"},
        "log": [{"at": "t", "event": "aborted", "by": "bob", "detail": "a bad day"}],
    }
    raw = {"workflow_id": WORKFLOW_ID, "status": "COMPLETED", "result": result}
    workflow, _ = make(answer(200, raw))
    run = await workflow.run(WORKFLOW_ID)
    assert run is not None
    assert (run.status, run.phase, run.outcome, run.steps_completed) == (
        "completed",
        None,
        "aborted",
        1,
    )
    assert (run.control_plane_version, run.mce, run.decisions) == (
        "4.18.56",
        "ocp4-prod-mce-site1-a",
        None,
    )
    assert run.plan is not None and run.plan.target == "4.18.56"


async def test_a_failed_run_keeps_its_error_and_a_wrongly_typed_field_is_left_out() -> None:
    progress = {"phase": "planning", "plan": "not a plan", "paused": "yes", "current_step": "1"}
    raw = {"workflow_id": WORKFLOW_ID, "status": "FAILED", "progress": progress, "error": "no"}
    workflow, _ = make(answer(200, raw))
    run = await workflow.run(WORKFLOW_ID)
    assert run is not None
    assert (run.status, run.phase, run.error) == ("failed", "planning", "no")
    assert (run.plan, run.paused, run.current_step) == (None, False, None)


async def test_no_run_is_none_and_a_bad_answer_is_unavailable() -> None:
    workflow, _ = make(answer(404, {"detail": "Workflow not found"}))
    assert await workflow.run(WORKFLOW_ID) is None
    for handler in (
        answer(500, {}),
        answer(200, {"status": "RUNNING"}),
        failing(httpx.ConnectError),
    ):
        workflow, _ = make(handler)
        with pytest.raises(WorkflowsUnavailableError):
            await workflow.run(WORKFLOW_ID)


# ── Metrics and the OpenAPI ──────────────────────────────────────────────────


async def test_targets_starts_and_decisions_are_counted_without_a_decision_label() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    calls: list[tuple[Handler, Callable[[HttpUpgradeWorkflow], Any]]] = [
        (answer(200, TARGETS_ANSWER), lambda w: w.targets(CLUSTER)),
        (answer(409, {}), lambda w: w.targets(CLUSTER)),
        (answer(202, {"workflow_id": WORKFLOW_ID}), lambda w: w.start(REQUEST)),
        (answer(409, {}), lambda w: w.start(REQUEST)),
        (answer(200, {}), lambda w: w.decide(WORKFLOW_ID, UpgradeDecision.APPROVE, by="a")),
        (answer(409, {}), lambda w: w.decide(WORKFLOW_ID, UpgradeDecision.RETRY, by="a")),
        (answer(504, {}), lambda w: w.decide_action(WORKFLOW_ID, "x", approve=True, by="a")),
    ]
    for handler, call in calls:
        workflow, _ = make(handler, metrics=metrics)
        with contextlib.suppress(Exception):
            await call(workflow)

    def count(operation: str, outcome: str) -> float | None:
        labels = {"dependency": "workflows", "operation": operation, "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert (count("upgrade_targets", "ok"), count("upgrade_targets", "rejected")) == (1.0, 1.0)
    assert (count("start_upgrade", "ok"), count("start_upgrade", "conflict")) == (1.0, 1.0)
    assert (count("decide_upgrade", "ok"), count("decide_upgrade", "conflict")) == (1.0, 1.0)
    assert count("decide_upgrade", "ambiguous") == 1.0


def _schema(document: dict[str, Any], path: str) -> dict[str, Any]:
    operation = document["paths"][path]["post"]
    ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    return document["components"]["schemas"][ref.rsplit("/", 1)[-1]]


def test_the_orchestrators_openapi_takes_what_day1_sends() -> None:
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    start = _schema(document, UPGRADE)
    sent = {
        "cluster",
        "requested_by",
        "target_version",
        "target_minor",
        "nodepool_order",
        "max_unavailable",
        "workers_to_target",
        "nodepool_mode",
        "auto_approve",
    }
    assert sent <= set(start["properties"])
    assert {"cluster", "requested_by"} <= set(start["required"])
    for decision in UpgradeDecision:
        schema = _schema(document, f"{UPGRADE}/{{workflow_id}}/{decision.value}")
        assert "by" in schema["required"]
        assert ("reason" in schema["properties"]) is decision.takes_reason, decision
        assert ("reason" in schema.get("required", [])) is decision.needs_reason, decision
        assert ("nodepool" in schema["properties"]) is (decision is UpgradeDecision.CONTINUE)
    for verdict in ("approve", "reject"):
        schema = _schema(document, f"{UPGRADE}/{{workflow_id}}/actions/{{action_id}}/{verdict}")
        assert set(schema["properties"]) == {"by"}
    targets = document["paths"][TARGETS]["get"]
    assert [p["name"] for p in targets["parameters"]] == ["cluster"]
