"""HttpUninstallWorkflow against the orchestrator's answers (MockTransport), and its cache.

A start is a write: it is sent once and never retried (ADR-0006). What
happens to it decides the answer: refused before it left is "nothing
started", sent and unanswered is ambiguous.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    UninstallAlreadyRunningError,
    WorkflowRefusedError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.servers import RunSummary
from wingman_day1.domain.workflows import WorkflowRun
from wingman_day1.infrastructure.cached_workflows import CachedUninstallWorkflow
from wingman_day1.infrastructure.workflows_api import HttpUninstallWorkflow

SERVER = "ocp-dell-r660-site1-64c-512gb-DL0000123"
WORKFLOW_ID = "uninstall-server-from-hc-ocp-dell-r660-site1-64c-512gb-dl0000123"
MCE = "ocp4-prod-mce-site1-a"
START_PATH = "/workflows/server-lifecycle/uninstall-server-from-hc"
OPENAPI = (
    Path(__file__).resolve().parents[5] / "docs/ecosystem/notes/workflows-orchestrator-openapi.json"
)

Handler = Callable[[httpx.Request], httpx.Response]


def make(
    handler: Handler, *, metrics: WingmanMetrics | None = None
) -> tuple[HttpUninstallWorkflow, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    workflow = HttpUninstallWorkflow(
        base_url="http://workflows-orchestrator-api.redbull-workflows.svc:8080/",
        timeout_seconds=2.0,
        metrics=metrics,
        transport=httpx.MockTransport(record),
        timer=iter(range(1000)).__next__,
    )
    return workflow, requests


def reply(status: int, body: object = None) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


def raising(exc: type[httpx.TransportError]) -> Handler:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exc("boom", request=request)

    return fail


async def start(workflow: HttpUninstallWorkflow, namespace: str | None = None) -> WorkflowRun:
    return await workflow.start(server_name=SERVER, mce=MCE, namespace=namespace)


async def test_a_start_sends_one_name_and_the_mce_and_answers_the_running_run() -> None:
    workflow, requests = make(reply(202, {"workflow_id": WORKFLOW_ID, "run_id": "r-1"}))
    assert await start(workflow) == WorkflowRun(WORKFLOW_ID, "running")
    request = requests[0]
    assert (request.method, request.url.path) == ("POST", START_PATH)
    assert request.url.host == "workflows-orchestrator-api.redbull-workflows.svc"
    assert json.loads(request.content) == {"server_names": SERVER, "mce_cluster": MCE}
    assert "authorization" not in request.headers, "the orchestrator has no auth"
    await workflow.aclose()


async def test_the_namespace_is_sent_only_when_set() -> None:
    workflow, requests = make(reply(202, {"workflow_id": WORKFLOW_ID, "run_id": "r-1"}))
    await start(workflow, namespace="hardware-inventory")
    assert json.loads(requests[0].content)["namespace"] == "hardware-inventory"


async def test_a_second_start_while_one_runs_is_already_running() -> None:
    workflow, requests = make(reply(409, {"detail": f"Workflow already running: {WORKFLOW_ID}"}))
    with pytest.raises(UninstallAlreadyRunningError, match=SERVER):
        await start(workflow)
    assert len(requests) == 1


async def test_a_body_the_orchestrator_refuses_is_refused_and_nothing_started() -> None:
    workflow, _ = make(reply(422, {"detail": [{"type": "extra_forbidden", "loc": ["body", "x"]}]}))
    with pytest.raises(WorkflowRefusedError, match=r"refused the uninstall .*\(422\)"):
        await start(workflow)


async def test_temporal_refusing_the_start_is_unavailable_with_its_reason() -> None:
    workflow, requests = make(reply(502, {"detail": "Temporal refused: namespace not found"}))
    with pytest.raises(
        WorkflowsUnavailableError, match=r"answered 502.*Temporal refused"
    ) as caught:
        await start(workflow)
    assert not isinstance(caught.value, WorkflowRefusedError)
    assert len(requests) == 1, "a refused start is not retried"


@pytest.mark.parametrize("exc", [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout])
async def test_a_start_that_never_left_is_unavailable_and_nothing_started(
    exc: type[httpx.TransportError],
) -> None:
    workflow, _ = make(raising(exc))
    with pytest.raises(WorkflowsUnavailableError, match="nothing was started"):
        await start(workflow)


@pytest.mark.parametrize(
    "exc", [httpx.ReadTimeout, httpx.ReadError, httpx.RemoteProtocolError, httpx.WriteTimeout]
)
async def test_a_start_sent_without_an_answer_is_ambiguous_and_not_retried(
    exc: type[httpx.TransportError],
) -> None:
    workflow, requests = make(raising(exc))
    with pytest.raises(AmbiguousStartError, match=r"may have started.*before trying again"):
        await start(workflow)
    assert len(requests) == 1


async def test_a_gateway_timeout_is_ambiguous() -> None:
    workflow, _ = make(reply(504, {}))
    with pytest.raises(AmbiguousStartError, match="may have started"):
        await start(workflow)


@pytest.mark.parametrize("body", [{"started": 1, "results": []}, ["x"], {"workflow_id": ""}])
async def test_an_accepted_start_with_an_unreadable_answer_is_ambiguous(body: object) -> None:
    workflow, _ = make(reply(202, body))
    with pytest.raises(AmbiguousStartError, match=r"accepted .*\(202\)"):
        await start(workflow)


async def test_the_run_list_asks_for_the_uninstall_class_and_the_most_runs() -> None:
    runs = [
        {
            "workflow_id": WORKFLOW_ID,
            "workflow_type": "UninstallServerFromHcWorkflow",
            "status": "RUNNING",
            "start_time": "2026-11-11T08:00:00Z",
            "close_time": None,
        },
        {
            "workflow_id": "uninstall-server-from-hc-other",
            "workflow_type": "UninstallServerFromHcWorkflow",
            "status": "FAILED",
            "start_time": "2026-11-10T08:00:00Z",
            "close_time": "2026-11-10T08:10:00Z",
        },
    ]
    workflow, requests = make(reply(200, runs))
    assert await workflow.runs() == [
        RunSummary(WORKFLOW_ID, "running"),
        RunSummary("uninstall-server-from-hc-other", "failed"),
    ]
    assert requests[0].url.path == "/workflows/runs"
    assert dict(requests[0].url.params) == {
        "workflow_type": "UninstallServerFromHcWorkflow",
        "limit": "200",
    }


async def test_one_run_carries_its_phase_and_error_passed_through() -> None:
    body = {
        "workflow_id": WORKFLOW_ID,
        "workflow_type": "UninstallServerFromHcWorkflow",
        "status": "FAILED",
        "progress": {"phase": "awaiting-machine-deletion", "sub_phase": "draining"},
        "result": None,
        "error": "ServerReservedError: held by install-server",
    }
    workflow, requests = make(reply(200, body))
    assert await workflow.run(WORKFLOW_ID) == WorkflowRun(
        WORKFLOW_ID,
        "failed",
        phase="awaiting-machine-deletion",
        error="ServerReservedError: held by install-server",
    )
    assert requests[0].url.path == f"/workflows/runs/{WORKFLOW_ID}"


async def test_a_run_without_progress_has_no_phase() -> None:
    body = {"workflow_id": WORKFLOW_ID, "workflow_type": "x", "status": "COMPLETED"}
    workflow, _ = make(reply(200, body))
    assert await workflow.run(WORKFLOW_ID) == WorkflowRun(WORKFLOW_ID, "completed")


async def test_an_unknown_run_is_none() -> None:
    workflow, _ = make(reply(404, {"detail": f"Workflow not found: {WORKFLOW_ID}"}))
    assert await workflow.run(WORKFLOW_ID) is None


@pytest.mark.parametrize(
    "handler",
    [reply(500, {}), reply(200, {"status": "RUNNING"}), raising(httpx.ReadTimeout)],
)
async def test_reads_that_fail_are_unavailable(handler: Handler) -> None:
    workflow, _ = make(handler)
    with pytest.raises(WorkflowsUnavailableError):
        await workflow.run(WORKFLOW_ID)


@pytest.mark.parametrize(
    "handler",
    [reply(503, {}), reply(200, {"items": []}), reply(200, [{"workflow_id": 3}])],
)
async def test_a_run_list_that_cannot_be_read_is_unavailable_not_empty(handler: Handler) -> None:
    workflow, _ = make(handler)
    with pytest.raises(WorkflowsUnavailableError):
        await workflow.runs()


async def test_calls_are_counted_by_operation_and_outcome() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    for handler, error in (
        (reply(202, {"workflow_id": WORKFLOW_ID, "run_id": "r"}), None),
        (reply(409, {}), UninstallAlreadyRunningError),
        (reply(422, {}), WorkflowRefusedError),
        (raising(httpx.ReadTimeout), AmbiguousStartError),
        (reply(502, {}), WorkflowsUnavailableError),
    ):
        workflow, _ = make(handler, metrics=metrics)
        if error is None:
            await start(workflow)
        else:
            with pytest.raises(error):
                await start(workflow)

    def count(outcome: str) -> float | None:
        labels = {"dependency": "workflows", "operation": "start_uninstall", "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert [count(o) for o in ("ok", "conflict", "rejected", "ambiguous", "unavailable")] == [
        1.0
    ] * 5


class CountingWorkflow:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_start: Exception | None = None

    async def runs(self) -> list[RunSummary]:
        self.calls.append("runs")
        return [RunSummary(WORKFLOW_ID, "running")]

    async def run(self, workflow_id: str) -> WorkflowRun | None:
        self.calls.append(f"run:{workflow_id}")
        return None

    async def start(self, *, server_name: str, mce: str, namespace: str | None) -> WorkflowRun:
        self.calls.append("start")
        if self.fail_start is not None:
            raise self.fail_start
        return WorkflowRun(WORKFLOW_ID, "running")


async def test_the_cache_keeps_runs_and_one_run_including_a_missing_one() -> None:
    inner = CountingWorkflow()
    cached = CachedUninstallWorkflow(inner, TtlCache(), ttl=10)
    for _ in range(2):
        await cached.runs()
        assert await cached.run(WORKFLOW_ID) is None
    assert inner.calls == ["runs", f"run:{WORKFLOW_ID}"]


@pytest.mark.parametrize(
    "failure", [None, AmbiguousStartError("lost"), UninstallAlreadyRunningError("busy")]
)
async def test_a_start_forgets_every_cached_run_whatever_its_answer(
    failure: Exception | None,
) -> None:
    inner = CountingWorkflow()
    inner.fail_start = failure
    cached = CachedUninstallWorkflow(inner, TtlCache(), ttl=10)
    await cached.runs()
    await cached.run(WORKFLOW_ID)
    try:
        await cached.start(server_name=SERVER, mce=MCE, namespace=None)
    except (AmbiguousStartError, UninstallAlreadyRunningError) as exc:
        assert exc is failure
    await cached.runs()
    await cached.run(WORKFLOW_ID)
    assert inner.calls.count("start") == 1, "a start is never retried"
    assert inner.calls.count("runs") == 2
    assert inner.calls.count(f"run:{WORKFLOW_ID}") == 2


def test_the_shapes_here_are_the_orchestrators_saved_openapi() -> None:
    """The adapter's paths and body keys are the ones the saved OpenAPI document declares."""
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    assert START_PATH in document["paths"]
    assert {"/workflows/runs", "/workflows/runs/{workflow_id}"} <= set(document["paths"])
    body = document["components"]["schemas"]["UninstallServerFromHcRequest"]
    assert set(body["properties"]) == {"server_names", "mce_cluster", "namespace"}
    assert set(body["required"]) == {"server_names", "mce_cluster"}
    assert body["additionalProperties"] is False
