"""HttpProvisionWorkflow against the orchestrator's answers (MockTransport), and its fake.

A start is a write: it is sent once and never retried (ADR-0006). What
happens to it decides the answer: refused before it left is "nothing
started", sent and unanswered is ambiguous (ADR-0042).
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import (
    AlreadyInUseError,
    AmbiguousStartError,
    InvalidInputError,
    ProvisionAlreadyRunningError,
    ProvisionRefusedError,
    WorkflowRefusedError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.workflows import ProvisionRun, provision_workflow_id
from wingman_day1.infrastructure.fake_provision import (
    DEMO_PHASES,
    PHASE_SECONDS,
    FakeProvisionWorkflow,
)
from wingman_day1.infrastructure.provision_workflow import HttpProvisionWorkflow

CLUSTER = "prod-rcs-site1-a"
STEM = f"ocp4-{CLUSTER}"
WORKFLOW_ID = f"provision-cluster-{STEM}"
MCE = "ocp4-prod-mce-site1-a"
START_PATH = "/workflows/cluster-lifecycle/provision-cluster"
FILE = '# wingman: spec rcs 1.0.0\nowner:\n  merkaz: "1"\nmastertag: 4.18.22-x86_64\nnodepool: []\n'
OPENAPI = (
    Path(__file__).resolve().parents[5] / "docs/ecosystem/notes/workflows-orchestrator-openapi.json"
)

Handler = Callable[[httpx.Request], httpx.Response]


def make(
    handler: Handler, *, metrics: WingmanMetrics | None = None
) -> tuple[HttpProvisionWorkflow, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    workflow = HttpProvisionWorkflow(
        base_url="http://workflows-orchestrator-api.redbull-workflows.svc:8080/",
        timeout_seconds=2.0,
        metrics=metrics,
        transport=httpx.MockTransport(record),
        timer=iter(range(1000)).__next__,
    )
    return workflow, requests


def answer(status: int, body: object) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


async def start(workflow: HttpProvisionWorkflow) -> ProvisionRun:
    return await workflow.start(cluster=CLUSTER, mce=MCE, content=FILE)


# ── Start ────────────────────────────────────────────────────────────────────


async def test_a_start_sends_the_file_as_yaml_with_cluster_and_mce_in_the_query() -> None:
    workflow, requests = make(answer(202, {"workflow_id": WORKFLOW_ID, "run_id": "r1"}))
    run = await start(workflow)
    assert run == ProvisionRun(WORKFLOW_ID, "running")
    assert run.cluster == STEM
    (request,) = requests
    assert request.method == "POST"
    assert request.url.path == START_PATH
    assert dict(request.url.params) == {"cluster": CLUSTER, "mce": MCE}
    assert request.headers["content-type"] == "application/yaml"
    assert request.content.decode() == FILE  # verbatim: comments and layout reach day1


async def test_a_run_already_going_is_a_conflict_and_nothing_is_sent_twice() -> None:
    workflow, requests = make(answer(409, {"detail": f"{WORKFLOW_ID} is already running"}))
    with pytest.raises(ProvisionAlreadyRunningError, match="already going") as caught:
        await start(workflow)
    assert isinstance(caught.value, AlreadyInUseError)  # 409 ALREADY_EXISTS
    assert len(requests) == 1


async def test_a_refused_name_or_file_lists_the_orchestrators_reasons() -> None:
    detail = [
        {"loc": ["query", "cluster"], "msg": "at most 24 characters", "type": "value_error"},
        {"loc": ["body"], "msg": "must be one YAML mapping", "type": "value_error"},
    ]
    workflow, _ = make(answer(422, {"detail": detail}))
    with pytest.raises(ProvisionRefusedError) as caught:
        await start(workflow)
    assert isinstance(caught.value, InvalidInputError)  # 422 VALIDATION_ERROR
    assert caught.value.problems == ("cluster: at most 24 characters", "must be one YAML mapping")


async def test_a_refusal_in_words_is_kept_as_one_problem() -> None:
    workflow, _ = make(answer(422, {"detail": "the body is empty"}))
    with pytest.raises(ProvisionRefusedError) as caught:
        await start(workflow)
    assert caught.value.problems == ("the body is empty",)


async def test_another_4xx_is_a_refusal_and_a_5xx_is_unavailable() -> None:
    workflow, _ = make(answer(400, {"detail": "bad"}))
    with pytest.raises(WorkflowRefusedError, match=r"\(400\): bad"):
        await start(workflow)
    workflow, _ = make(answer(502, {"detail": "temporal refused"}))
    with pytest.raises(WorkflowsUnavailableError, match="answered 502"):
        await start(workflow)


async def test_a_gateway_timeout_or_a_lost_answer_is_ambiguous() -> None:
    workflow, _ = make(answer(504, {}))
    with pytest.raises(AmbiguousStartError, match="may have started"):
        await start(workflow)

    def lost(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("no answer")

    workflow, requests = make(lost)
    with pytest.raises(AmbiguousStartError, match="ReadTimeout"):
        await start(workflow)
    assert len(requests) == 1  # never retried


async def test_an_unreachable_orchestrator_started_nothing() -> None:
    def refused(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    workflow, _ = make(refused)
    with pytest.raises(WorkflowsUnavailableError, match="nothing was started"):
        await start(workflow)


async def test_an_unreadable_202_is_ambiguous() -> None:
    workflow, _ = make(lambda _r: httpx.Response(202, text="accepted"))
    with pytest.raises(AmbiguousStartError, match="could not be read"):
        await start(workflow)


# ── Read ─────────────────────────────────────────────────────────────────────


async def test_a_run_shows_its_own_phase_merge_request_and_error() -> None:
    body = {
        "workflow_id": WORKFLOW_ID,
        "workflow_type": "ProvisionClusterWorkflow",
        "status": "RUNNING",
        "progress": {
            "phase": "awaiting-merge",
            "branch": f"provision-cluster/{STEM}",
            "merge_request_url": "https://gitlab.example/p/-/merge_requests/42",
            "merge_request_state": "opened",
            "polls": 7,
        },
    }
    workflow, requests = make(answer(200, body))
    run = await workflow.run(WORKFLOW_ID)
    assert run == ProvisionRun(
        WORKFLOW_ID,
        "running",
        phase="awaiting-merge",
        merge_request_url="https://gitlab.example/p/-/merge_requests/42",
        merge_request_state="opened",
    )
    assert requests[0].url.path == f"/workflows/runs/{WORKFLOW_ID}"


async def test_a_failed_run_keeps_the_workflows_words() -> None:
    body = {
        "workflow_id": WORKFLOW_ID,
        "workflow_type": "ProvisionClusterWorkflow",
        "status": "FAILED",
        "progress": {"phase": "inspecting-target", "merge_request_url": None},
        "error": "ClusterAlreadyProvisionedError: the file is already on main",
    }
    workflow, _ = make(answer(200, body))
    run = await workflow.run(WORKFLOW_ID)
    assert run is not None
    assert (run.status, run.phase, run.merge_request_url) == ("failed", "inspecting-target", None)
    assert run.error == "ClusterAlreadyProvisionedError: the file is already on main"


async def test_a_completed_run_takes_the_merge_request_from_its_result() -> None:
    body = {
        "workflow_id": WORKFLOW_ID,
        "workflow_type": "ProvisionClusterWorkflow",
        "status": "COMPLETED",
        "progress": None,
        "result": {"merge_request_url": "https://gitlab.example/p/-/merge_requests/42"},
    }
    workflow, _ = make(answer(200, body))
    run = await workflow.run(WORKFLOW_ID)
    assert run is not None
    assert run.status == "completed"
    assert run.merge_request_url == "https://gitlab.example/p/-/merge_requests/42"


async def test_no_run_is_none_and_a_bad_answer_is_unavailable() -> None:
    workflow, _ = make(answer(404, {"detail": "unknown"}))
    assert await workflow.run(WORKFLOW_ID) is None
    workflow, _ = make(answer(200, ["not", "a", "run"]))
    with pytest.raises(WorkflowsUnavailableError, match="malformed"):
        await workflow.run(WORKFLOW_ID)
    workflow, _ = make(answer(500, {}))
    with pytest.raises(WorkflowsUnavailableError, match="answered 500"):
        await workflow.run(WORKFLOW_ID)


# ── Metrics and the OpenAPI ──────────────────────────────────────────────────


async def test_starts_are_counted_under_start_provision() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    for handler in (answer(202, {"workflow_id": WORKFLOW_ID}), answer(409, {}), answer(422, {})):
        workflow, _ = make(handler, metrics=metrics)
        with contextlib.suppress(ProvisionAlreadyRunningError, ProvisionRefusedError):
            await start(workflow)

    def count(outcome: str) -> float | None:
        labels = {"dependency": "workflows", "operation": "start_provision", "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert (count("ok"), count("conflict"), count("rejected")) == (1.0, 1.0, 1.0)


def test_the_orchestrators_openapi_has_the_route_day1_calls() -> None:
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    operation = document["paths"][START_PATH]["post"]
    assert {p["name"]: p["in"] for p in operation["parameters"]} == {
        "cluster": "query",
        "mce": "query",
    }
    assert "application/yaml" in operation["requestBody"]["content"]
    assert "202" in operation["responses"]


# ── The fake ─────────────────────────────────────────────────────────────────


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


async def test_the_fake_walks_sample_phases_and_then_waits_for_its_merge_request() -> None:
    clock = Clock()
    fake = FakeProvisionWorkflow(clock=clock)
    started = await fake.start(cluster=CLUSTER, mce=MCE, content=FILE)
    assert started.workflow_id == provision_workflow_id(STEM)
    run = await fake.run(started.workflow_id)
    assert run is not None
    assert (run.phase, run.merge_request_url) == (DEMO_PHASES[0], None)
    clock.now += timedelta(seconds=PHASE_SECONDS * 10)
    run = await fake.run(started.workflow_id)
    assert run is not None
    assert (run.status, run.phase) == ("running", "awaiting-merge")
    assert run.merge_request_url is not None
    assert run.merge_request_url.startswith("https://gitlab.example/")
    with pytest.raises(ProvisionAlreadyRunningError):
        await fake.start(cluster=CLUSTER, mce=MCE, content=FILE)


async def test_the_fake_fails_a_file_without_a_mastertag_inside_the_run() -> None:
    fake = FakeProvisionWorkflow()
    started = await fake.start(cluster=CLUSTER, mce=MCE, content="owner: {}\n")
    run = await fake.run(started.workflow_id)
    assert run is not None
    assert run.status == "failed"
    assert run.error is not None
    assert "mastertag" in run.error
    assert await fake.run("provision-cluster-ocp4-nobody") is None
