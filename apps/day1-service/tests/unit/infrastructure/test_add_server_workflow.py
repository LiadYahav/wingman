"""HttpAddServerWorkflow against the orchestrator's answers (MockTransport), ADR-0057.

A start is a write: it is sent once and never retried (ADR-0006). Refused
before it left is "nothing started"; sent and unanswered is ambiguous: some
runs may exist.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.add_server import AddServerRequest, AddServerStart, StartedRun
from wingman_day1.domain.errors import (
    AddServerAlreadyRunningError,
    AddServerRefusedError,
    AmbiguousStartError,
    InvalidInputError,
    WorkflowRefusedError,
    WorkflowsUnavailableError,
)
from wingman_day1.infrastructure.add_server_workflow import HttpAddServerWorkflow
from wingman_day1.infrastructure.cached_workflows import CachedAddServerWorkflow

MCE = "ocp4-prod-mce-site1-a"
POOL = "dell-r650-site1-96c-768gb"
SERVER = "ocp-dell-r650-site1-96c-768gb-DLFAKE0811"
START_PATH = "/workflows/server-lifecycle/add-server-to-mce"
SLOT_1 = f"add-server-to-mce-{MCE}_{POOL}_1"
SLOT_2 = f"add-server-to-mce-{MCE}_{POOL}_2"
OPENAPI = (
    Path(__file__).resolve().parents[5] / "docs/ecosystem/notes/workflows-orchestrator-openapi.json"
)

Handler = Callable[[httpx.Request], httpx.Response]


def make(
    handler: Handler, *, metrics: WingmanMetrics | None = None
) -> tuple[HttpAddServerWorkflow, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    workflow = HttpAddServerWorkflow(
        base_url="http://workflows-orchestrator-api.redbull-workflows.svc:8080/",
        timeout_seconds=2.0,
        metrics=metrics,
        transport=httpx.MockTransport(record),
        timer=iter(range(1000)).__next__,
    )
    return workflow, requests


def answer(status: int, body: object) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


def raises(error: Exception) -> Handler:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise error

    return handler


BY_COUNT = AddServerRequest(MCE, POOL, "inventory", count=2)
BY_NAME = AddServerRequest(MCE, POOL, None, server_names=(SERVER,))
BATCH = {
    "started": 2,
    "already_running": 0,
    "failed": 0,
    "results": [
        {"workflow_id": SLOT_1, "status": "started", "slot": 1, "run_id": "r1"},
        {"workflow_id": SLOT_2, "status": "started", "slot": 2, "run_id": "r2"},
    ],
}


# ── Start ────────────────────────────────────────────────────────────────────


async def test_a_count_is_sent_once_with_the_pool_and_answered_per_run() -> None:
    workflow, requests = make(answer(202, BATCH))
    result = await workflow.start(BY_COUNT)
    assert result == AddServerStart(
        2, 0, 0, (StartedRun(SLOT_1, "started", slot=1), StartedRun(SLOT_2, "started", slot=2))
    )
    assert len(requests) == 1
    assert (requests[0].method, requests[0].url.path) == ("POST", START_PATH)
    assert json.loads(requests[0].content) == {
        "infra_env": POOL,
        "mce_cluster": MCE,
        "namespace": "inventory",
        "count": 2,
    }


async def test_names_are_always_sent_as_a_list_and_no_namespace_when_unset() -> None:
    named = f"add-server-to-mce-{MCE}_{SERVER.lower()}"
    body = {
        "started": 0,
        "already_running": 1,
        "failed": 0,
        "results": [{"workflow_id": named, "status": "already_running", "server_name": SERVER}],
    }
    workflow, requests = make(answer(202, body))
    result = await workflow.start(BY_NAME)
    assert json.loads(requests[0].content) == {
        "infra_env": POOL,
        "mce_cluster": MCE,
        "server_names": [SERVER],
    }
    assert result.already_running == 1
    assert result.runs == (StartedRun(named, "already_running", server_name=SERVER),)


async def test_a_lone_runs_answer_is_read_too() -> None:
    workflow, _ = make(answer(202, {"workflow_id": SLOT_1, "run_id": "r1"}))
    assert await workflow.start(BY_COUNT) == AddServerStart(
        1, 0, 0, (StartedRun(SLOT_1, "started"),)
    )


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (409, {"detail": "every slot is busy"}, AddServerAlreadyRunningError),
        (422, {"detail": [{"loc": ["body", "count"], "msg": "too many"}]}, AddServerRefusedError),
        (400, {"detail": "bad"}, WorkflowRefusedError),
        (502, {"detail": "Temporal refused"}, WorkflowsUnavailableError),
        (504, {}, AmbiguousStartError),
    ],
)
async def test_the_orchestrators_refusals(
    status: int, body: object, error: type[Exception]
) -> None:
    workflow, requests = make(answer(status, body))
    with pytest.raises(error):
        await workflow.start(BY_COUNT)
    assert len(requests) == 1, "never retried"


async def test_a_422_carries_the_orchestrators_findings() -> None:
    body = {"detail": [{"loc": ["body", "count"], "msg": "Input should be less than 21"}]}
    workflow, _ = make(answer(422, body))
    with pytest.raises(InvalidInputError) as caught:
        await workflow.start(BY_COUNT)
    assert caught.value.problems == ("count: Input should be less than 21",)


async def test_not_sent_is_nothing_started_and_unanswered_is_ambiguous() -> None:
    workflow, _ = make(raises(httpx.ConnectError("refused")))
    with pytest.raises(WorkflowsUnavailableError, match="nothing was started"):
        await workflow.start(BY_COUNT)
    workflow, requests = make(raises(httpx.ReadTimeout("slow")))
    with pytest.raises(AmbiguousStartError, match="some may have started"):
        await workflow.start(BY_COUNT)
    assert len(requests) == 1


async def test_an_unreadable_202_is_ambiguous() -> None:
    workflow, _ = make(answer(202, {"results": "nope"}))
    with pytest.raises(AmbiguousStartError):
        await workflow.start(BY_COUNT)


# ── Reads ────────────────────────────────────────────────────────────────────


async def test_the_run_list_is_filtered_by_type_and_carries_times() -> None:
    body = [
        {
            "workflow_id": SLOT_1,
            "workflow_type": "AddServerToMceWorkflow",
            "status": "RUNNING",
            "start_time": "2026-11-13T12:00:00Z",
            "close_time": None,
        }
    ]
    workflow, requests = make(answer(200, body))
    [run] = await workflow.runs()
    assert requests[0].url.params["workflow_type"] == "AddServerToMceWorkflow"
    assert requests[0].url.params["limit"] == "200"
    assert (run.workflow_id, run.status, run.closed_at) == (SLOT_1, "running", None)
    assert run.started_at == datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


async def test_one_run_has_its_phase_server_and_error() -> None:
    body = {
        "workflow_id": SLOT_1,
        "status": "FAILED",
        "progress": {"phase": "acquiring-server", "server_name": SERVER},
        "error": {"ServerReservedError": [SERVER]},
    }
    workflow, requests = make(answer(200, body))
    run = await workflow.run(SLOT_1)
    assert run is not None
    assert (run.status, run.phase, run.server_name) == ("failed", "acquiring-server", SERVER)
    assert run.error == '{"ServerReservedError":["ocp-dell-r650-site1-96c-768gb-DLFAKE0811"]}'
    assert requests[0].url.path == f"/workflows/runs/{SLOT_1}"


async def test_a_missing_run_is_none_and_a_failed_read_is_unavailable() -> None:
    workflow, _ = make(answer(404, {}))
    assert await workflow.run(SLOT_1) is None
    workflow, _ = make(answer(500, {}))
    with pytest.raises(WorkflowsUnavailableError):
        await workflow.runs()
    workflow, _ = make(answer(200, {"not": "a list"}))
    with pytest.raises(WorkflowsUnavailableError, match="malformed"):
        await workflow.runs()


# ── Metrics and the OpenAPI ──────────────────────────────────────────────────


async def test_starts_are_counted_under_start_add_server() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    for handler in (answer(202, BATCH), answer(409, {}), answer(422, {}), answer(504, {})):
        workflow, _ = make(handler, metrics=metrics)
        with contextlib.suppress(
            AddServerAlreadyRunningError, AddServerRefusedError, AmbiguousStartError
        ):
            await workflow.start(BY_COUNT)

    def count(outcome: str) -> float | None:
        labels = {"dependency": "workflows", "operation": "start_add_server", "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert [count(o) for o in ("ok", "conflict", "rejected", "ambiguous")] == [1.0] * 4


def test_the_orchestrators_openapi_takes_the_body_day1_sends() -> None:
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    operation = document["paths"][START_PATH]["post"]
    schema = document["components"]["schemas"]["AddServerToMceRequest"]
    assert schema["additionalProperties"] is False
    assert {"infra_env", "mce_cluster", "namespace", "count", "server_names"} <= set(
        schema["properties"]
    )
    assert "202" in operation["responses"]
    batch = document["components"]["schemas"]["AddServerToMceBatchResponse"]
    assert set(batch["required"]) == {"started", "already_running", "failed", "results"}


# ── The cache ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("start_status", [202, 504])
async def test_the_cache_reads_once_per_ttl_and_a_start_forgets_it(start_status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(start_status, json=BATCH)
        if request.url.path.endswith("/runs"):
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={})

    inner, requests = make(handler)
    cached = CachedAddServerWorkflow(inner, TtlCache(), ttl=10)
    for _ in range(2):
        assert await cached.runs() == []
        assert await cached.run(SLOT_1) is None
    assert len(requests) == 2
    with contextlib.suppress(AmbiguousStartError):
        await cached.start(BY_COUNT)
    await cached.runs()
    assert [r.method for r in requests] == ["GET", "GET", "POST", "GET"]
