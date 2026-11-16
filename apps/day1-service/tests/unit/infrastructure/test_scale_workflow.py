"""HttpScaleWorkflow against the orchestrator's answers (MockTransport, ADR-0062).

A start is a write: sent once, never retried (ADR-0006). Refused before it
left is "nothing sent"; sent and unanswered may have happened. The run is
read leniently, its child's phase by the child's own id. The bodies and the
answers are the update-nodepool branch's (``UpdateNodePoolRequest``,
``UpdateNodePoolResult``, the design page's example), which forbids any
field it does not name.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    InvalidInputError,
    ScaleAlreadyRunningError,
    ScaleRefusedError,
    WorkflowRefusedError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.scale import (
    ChosenServer,
    LiveReplicas,
    NodePoolChange,
    ScaleChild,
    ScaleRequest,
    scale_workflow_id,
)
from wingman_day1.infrastructure.scale_workflow import HttpScaleWorkflow

CLUSTER = "ocp4-prod-alpha"
RUN = scale_workflow_id(CLUSTER)
CHILD = f"scale-down-nodepool-{CLUSTER}"
START = "/workflows/server-lifecycle/update-nodepool"
BY_KIND = ScaleRequest("mce-bat-yam-01", CLUSTER, 10, infra_env_kind="cisco-m6-bat-yam-64c-512gb")
BY_NAME = ScaleRequest("mce-bat-yam-01", CLUSTER, 5, nodepool="prod-alpha-zone-c")
BUSY = (
    "upgrade-cluster-ocp4-prod-alpha is running: a replicas commit now would change the file "
    "under the upgrade, which would stop for a person at its next commit. Run update-nodepool "
    "once the upgrade has finished"
)
COMPLETED: dict[str, Any] = {
    "workflow_id": RUN,
    "workflow_type": "UpdateNodePoolWorkflow",
    "status": "COMPLETED",
    "result": {
        "mce_cluster": "ocp4-mce-bat-yam-01",
        "cluster": CLUSTER,
        "infra_env_kind": "cisco-m6-bat-yam-64c-512gb",
        "nodepool": None,
        "day1_path": f"sites/bat-yam/mces/ocp4-mce-bat-yam-01/hostedClusters/{CLUSTER}.yaml",
        "hosted_cluster": "openshift-prod-alpha",
        "hosted_cluster_namespace": "hcp-prod-alpha",
        "direction": "down",
        "total_before": 9,
        "total_after": 8,
        "nodepools": [
            {
                "name": "prod-alpha-zone-a",
                "infra_env": "cisco-m6-bat-yam-64c-512gb-zone-a",
                "before": 3,
                "after": 3,
            },
            {
                "name": "prod-alpha-zone-c",
                "infra_env": "cisco-m6-bat-yam-64c-512gb-zone-c",
                "before": 3,
                "after": 2,
                "scale_down_policy": "fewest-pods",
            },
            {"infra_env": "no-name-is-left-out", "before": 1, "after": 1},
        ],
        "child_workflow_id": CHILD,
        "scale": {
            "revision": "9f2c",
            "committed": True,
            "nodepools": [{"name": "prod-alpha-zone-c", "replicas": 2, "ready_replicas": 3}],
            "chosen": [
                {
                    "nodepool": "prod-alpha-zone-c",
                    "machine": "prod-alpha-zone-c-7xk2p",
                    "node": "worker-7",
                    "policy": "fewest-pods",
                    "reason": "1 workload pods",
                }
            ],
            "deleting": ["prod-alpha-zone-c-7xk2p", 7],
        },
        "added_later": {"ignored": True},
    },
}

Handler = Callable[[httpx.Request], httpx.Response]


def make(
    handler: Handler, *, metrics: WingmanMetrics | None = None
) -> tuple[HttpScaleWorkflow, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    workflow = HttpScaleWorkflow(
        base_url="http://workflows-orchestrator-api.redbull-workflows.svc:8080/",
        timeout_seconds=2.0,
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


# ── The start ────────────────────────────────────────────────────────────────


async def test_a_start_by_kind_sends_exactly_the_workflows_fields() -> None:
    workflow, requests = make(answer(202, {"workflow_id": RUN, "run_id": "r1"}))
    run = await workflow.start(BY_KIND)
    assert (run.workflow_id, run.status) == (RUN, "running")
    (sent,) = requests
    assert (sent.method, sent.url.path) == ("POST", START)
    assert json.loads(sent.content) == {
        "mce_cluster": "mce-bat-yam-01",
        "cluster": CLUSTER,
        "replicas": 10,
        "infra_env_kind": "cisco-m6-bat-yam-64c-512gb",
    }


async def test_a_start_by_nodepool_sends_the_nodepool_and_no_kind() -> None:
    workflow, requests = make(answer(202, {"workflow_id": RUN, "run_id": "r1"}))
    await workflow.start(BY_NAME)
    assert json.loads(requests[0].content) == {
        "mce_cluster": "mce-bat-yam-01",
        "cluster": CLUSTER,
        "replicas": 5,
        "nodepool": "prod-alpha-zone-c",
    }


async def test_a_409_keeps_the_orchestrators_words() -> None:
    workflow, _ = make(answer(409, {"detail": BUSY}))
    with pytest.raises(ScaleAlreadyRunningError) as raised:
        await workflow.start(BY_KIND)
    assert str(raised.value) == BUSY


async def test_a_422_lists_what_the_orchestrator_refused() -> None:
    detail = [{"loc": ["body", "nodepool"], "msg": "String should match pattern"}]
    workflow, _ = make(answer(422, {"detail": detail}))
    with pytest.raises(ScaleRefusedError) as raised:
        await workflow.start(BY_NAME)
    assert isinstance(raised.value, InvalidInputError)
    assert raised.value.problems == ("nodepool: String should match pattern",)


@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (failing(httpx.ConnectError), WorkflowsUnavailableError),
        (failing(httpx.ReadTimeout), AmbiguousStartError),
        (answer(504, {}), AmbiguousStartError),
        (answer(202, {"run_id": "no id"}), AmbiguousStartError),
        (answer(400, {"detail": "bad"}), WorkflowRefusedError),
        (answer(500, {}), WorkflowsUnavailableError),
    ],
)
async def test_a_start_is_never_retried_and_says_whether_it_may_have_happened(
    handler: Handler, error: type[Exception]
) -> None:
    workflow, requests = make(handler)
    with pytest.raises(error):
        await workflow.start(BY_KIND)
    assert len(requests) == 1


# ── The run ──────────────────────────────────────────────────────────────────


async def test_no_run_is_none() -> None:
    workflow, _ = make(answer(404, {"detail": f"Workflow not found: {RUN}"}))
    assert await workflow.run(RUN) is None


async def test_a_running_run_reads_its_childs_phase_by_the_childs_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(CHILD):
            return httpx.Response(
                200,
                json={
                    "workflow_id": CHILD,
                    "status": "RUNNING",
                    "progress": {"phase": "marking-machines"},
                },
            )
        return httpx.Response(
            200,
            json={
                "workflow_id": RUN,
                "status": "RUNNING",
                "progress": {
                    "phase": "scaling-down",
                    "direction": "down",
                    "child_workflow_id": CHILD,
                    "something_new": 1,
                },
            },
        )

    workflow, requests = make(handler)
    run = await workflow.run(RUN)
    assert run is not None
    assert (run.status, run.phase, run.direction) == ("running", "scaling-down", "down")
    assert run.child == ScaleChild(CHILD, "running", "marking-machines")
    assert [r.url.path for r in requests] == [
        f"/workflows/runs/{RUN}",
        f"/workflows/runs/{CHILD}",
    ]


async def test_a_child_that_cannot_be_read_leaves_the_parent_shown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(CHILD):
            return httpx.Response(503, json={})
        return httpx.Response(
            200,
            json={
                "workflow_id": RUN,
                "status": "RUNNING",
                "progress": {"phase": "scaling-up", "child_workflow_id": CHILD},
            },
        )

    workflow, _ = make(handler)
    run = await workflow.run(RUN)
    assert run is not None and run.child == ScaleChild(CHILD)


async def test_a_completed_run_carries_the_plan_the_servers_chosen_and_the_commit() -> None:
    workflow, requests = make(answer(200, COMPLETED))
    run = await workflow.run(RUN)
    assert run is not None and run.result is not None
    assert len(requests) == 1  # its child's result is in its own
    result = run.result
    assert (run.status, run.direction, run.child) == ("completed", "down", None)
    assert (result.direction, result.total_before, result.total_after) == ("down", 9, 8)
    assert result.nodepools == (
        NodePoolChange("prod-alpha-zone-a", "cisco-m6-bat-yam-64c-512gb-zone-a", 3, 3),
        NodePoolChange(
            "prod-alpha-zone-c", "cisco-m6-bat-yam-64c-512gb-zone-c", 3, 2, "fewest-pods"
        ),
    )
    assert (result.revision, result.committed, result.child_workflow_id) == ("9f2c", True, CHILD)
    assert result.live == (LiveReplicas("prod-alpha-zone-c", 2, 3),)
    assert result.chosen == (
        ChosenServer(
            "prod-alpha-zone-c",
            "prod-alpha-zone-c-7xk2p",
            "worker-7",
            "fewest-pods",
            "1 workload pods",
        ),
    )
    assert result.deleting == ("prod-alpha-zone-c-7xk2p",)


async def test_a_failed_run_keeps_its_words_its_phase_and_the_childs_failure() -> None:
    error = (
        f"{CHILD} failed — ArgoSyncRefusedError: something else is out of sync in the "
        "Application. Its history has the detail; running update-nodepool again carries on"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(CHILD):
            return httpx.Response(
                200,
                json={
                    "workflow_id": CHILD,
                    "status": "FAILED",
                    "progress": {"phase": "syncing-argo"},
                    "error": "something else is out of sync in the Application",
                },
            )
        return httpx.Response(
            200,
            json={
                "workflow_id": RUN,
                "status": "FAILED",
                "progress": {
                    "phase": "scaling-down",
                    "direction": "down",
                    "child_workflow_id": CHILD,
                },
                "error": error,
            },
        )

    workflow, _ = make(handler)
    run = await workflow.run(RUN)
    assert run is not None
    assert (run.status, run.error, run.error_type) == ("failed", error, "ArgoSyncRefusedError")
    assert run.child == ScaleChild(
        CHILD, "failed", "syncing-argo", "something else is out of sync in the Application"
    )


@pytest.mark.parametrize(
    "handler",
    [
        answer(500, {}),
        answer(200, {"status": "RUNNING"}),
        answer(200, ["not", "a", "run"]),
        lambda _r: httpx.Response(200, content=b"<html>"),
        failing(httpx.ConnectError),
    ],
)
async def test_an_unreadable_run_is_the_orchestrator_unavailable(handler: Handler) -> None:
    workflow, _ = make(handler)
    with pytest.raises(WorkflowsUnavailableError):
        await workflow.run(RUN)


# ── Metrics ──────────────────────────────────────────────────────────────────


async def test_starts_and_reads_are_counted_with_bounded_labels() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    calls: list[tuple[Handler, Callable[[HttpScaleWorkflow], Any]]] = [
        (answer(202, {"workflow_id": RUN}), lambda w: w.start(BY_KIND)),
        (answer(409, {"detail": BUSY}), lambda w: w.start(BY_NAME)),
        (answer(422, {"detail": "no"}), lambda w: w.start(BY_NAME)),
        (answer(504, {}), lambda w: w.start(BY_NAME)),
        (answer(200, COMPLETED), lambda w: w.run(RUN)),
    ]
    for handler, call in calls:
        workflow, _ = make(handler, metrics=metrics)
        with contextlib.suppress(Exception):
            await call(workflow)

    def count(operation: str, outcome: str) -> float | None:
        labels = {"dependency": "workflows", "operation": operation, "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert [
        count("start_update_nodepool", o) for o in ("ok", "conflict", "rejected", "ambiguous")
    ] == [1.0, 1.0, 1.0, 1.0]
    assert count("get_run", "ok") == 1.0
