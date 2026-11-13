"""HttpAddServerWorkflow: the orchestrator's add-server-to-mce workflow, over httpx (ADR-0057).

The workflow makes servers Agents in an MCE's InfraEnv pool. Day1 starts runs
and reads them:

- ``POST /workflows/server-lifecycle/add-server-to-mce`` with
  ``{"infra_env", "mce_cluster", "namespace"?, "count" | "server_names"}``.
  Day1 always sends a count or a list, so the orchestrator answers ``202
  {"started", "already_running", "failed", "results": [{"workflow_id",
  "status", "server_name"?, "slot"?, "error"?}]}`` (a lone run's ``202
  {"workflow_id", "run_id"}`` is read too). 409 for a named server already
  installing or every slot busy, 422 for a body it refuses, 502 when
  Temporal refuses. Every other refusal is a FAILED run, never a 4xx here.
- ``GET /workflows/runs?workflow_type=AddServerToMceWorkflow&limit=200``
  lists the fleet's newest runs; ``GET /workflows/runs/{id}`` is one run,
  with ``progress.phase`` and ``progress.server_name`` (404: no run).

A start is a write and is never retried (ADR-0006): sent twice, a pool draw
installs twice. Refused before it was sent (no connection), it is
``WorkflowsUnavailableError``; sent and unanswered, ``AmbiguousStartError``:
some runs may exist.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from datetime import datetime
from typing import Final
from urllib.parse import quote

import httpx

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.add_server import (
    AddServerRequest,
    AddServerRun,
    AddServerStart,
    ListedRun,
    StartedRun,
)
from wingman_day1.domain.errors import (
    AddServerAlreadyRunningError,
    AddServerRefusedError,
    AmbiguousStartError,
    WorkflowRefusedError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.servers import run_status
from wingman_day1.infrastructure.http import JSON, NOT_SENT, json_client
from wingman_day1.infrastructure.observed import Observer, Timer, WorkflowsOperation
from wingman_day1.infrastructure.provision_workflow import orchestrator_problems
from wingman_day1.infrastructure.workflows_api import RUNS_PATH, orchestrator_detail

START_PATH: Final = "/workflows/server-lifecycle/add-server-to-mce"
WORKFLOW_TYPE: Final = "AddServerToMceWorkflow"
"""The Temporal class name the run list filters on."""
RUNS_LIMIT: Final = 200
CHECK_FIRST: Final = "Look at the pool's add-server runs before asking again."
MAX_ERROR: Final = 500


class HttpAddServerWorkflow:
    """An ``AddServerWorkflow`` over the orchestrator's REST API."""

    def __init__(
        self,
        *,
        base_url: str,
        verify: bool | str = True,
        timeout_seconds: float = 10.0,
        metrics: WingmanMetrics | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timer: Timer = time.perf_counter,
    ) -> None:
        """Call the orchestrator at ``base_url``; ``verify`` is ``True``/``False`` or a CA path."""
        self._observer = Observer(Dependency.WORKFLOWS, metrics, timer=timer)
        self._client = json_client(
            base_url=base_url, verify=verify, timeout_seconds=timeout_seconds, transport=transport
        )

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def runs(self) -> list[ListedRun]:
        """See AddServerWorkflow.runs."""
        return await self._observer.call(WorkflowsOperation.LIST_RUNS, self._runs())

    async def run(self, workflow_id: str) -> AddServerRun | None:
        """See AddServerWorkflow.run."""
        return await self._observer.call(WorkflowsOperation.GET_RUN, self._run(workflow_id))

    async def start(self, request: AddServerRequest) -> AddServerStart:
        """See AddServerWorkflow.start."""
        return await self._observer.call(WorkflowsOperation.START_ADD_SERVER, self._start(request))

    async def _runs(self) -> list[ListedRun]:
        params = {"workflow_type": WORKFLOW_TYPE, "limit": RUNS_LIMIT}
        response = await self._read(RUNS_PATH, what="listing add-server runs", params=params)
        if response.status_code != 200:
            raise WorkflowsUnavailableError(
                f"the orchestrator answered {response.status_code} listing add-server runs"
            )
        try:
            return listed_runs(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise WorkflowsUnavailableError(
                "the orchestrator returned a malformed run list"
            ) from exc

    async def _run(self, workflow_id: str) -> AddServerRun | None:
        what = f"reading run {workflow_id}"
        response = await self._read(f"{RUNS_PATH}/{quote(workflow_id, safe='')}", what=what)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise WorkflowsUnavailableError(
                f"the orchestrator answered {response.status_code} {what}"
            )
        try:
            return add_server_run(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise WorkflowsUnavailableError(
                f"the orchestrator returned a malformed run {workflow_id}"
            ) from exc

    async def _read(
        self, path: str, *, what: str, params: Mapping[str, str | int] | None = None
    ) -> httpx.Response:
        try:
            return await self._client.get(path, params=params)
        except httpx.TransportError as exc:
            raise WorkflowsUnavailableError(
                f"the orchestrator is unreachable {what}: {type(exc).__name__}"
            ) from exc

    async def _start(self, request: AddServerRequest) -> AddServerStart:
        what = f"adding {request.size} server(s) to {request.infra_env} on {request.mce}"
        try:
            response = await self._client.post(START_PATH, json=start_body(request))
        except NOT_SENT as exc:
            raise WorkflowsUnavailableError(
                f"the orchestrator could not be reached for {what} ({type(exc).__name__}); "
                "nothing was started"
            ) from exc
        except httpx.TransportError as exc:
            raise AmbiguousStartError(
                f"{what} was sent but no answer came back ({type(exc).__name__}): some may "
                f"have started. {CHECK_FIRST}"
            ) from exc
        return _answer(response, what)


def _answer(response: httpx.Response, what: str) -> AddServerStart:
    status = response.status_code
    if status == 202:
        try:
            return started(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise AmbiguousStartError(
                f"the orchestrator accepted {what} (202) but its answer could not be read. "
                f"{CHECK_FIRST}"
            ) from exc
    detail = orchestrator_detail(response)
    if status == 409:
        raise AddServerAlreadyRunningError(f"the orchestrator refused {what}{detail}")
    if status == 422:
        raise AddServerRefusedError(
            f"the orchestrator refused {what}", orchestrator_problems(response)
        )
    if status == 504:
        raise AmbiguousStartError(
            f"a gateway timed out waiting for the orchestrator on {what}: some may have "
            f"started. {CHECK_FIRST}"
        )
    if 400 <= status < 500:
        raise WorkflowRefusedError(f"the orchestrator refused {what} ({status}){detail}")
    raise WorkflowsUnavailableError(f"the orchestrator answered {status} to {what}{detail}")


def start_body(request: AddServerRequest) -> dict[str, object]:
    """The start's JSON: always a count or a list, so the answer is always per run."""
    body: dict[str, object] = {"infra_env": request.infra_env, "mce_cluster": request.mce}
    if request.namespace:
        body["namespace"] = request.namespace
    if request.count is not None:
        body["count"] = request.count
    else:
        body["server_names"] = list(request.server_names)
    return body


def _text(raw: Mapping[str, JSON], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) and value else None


def _int(raw: Mapping[str, JSON], key: str) -> int | None:
    value = raw.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _object(raw: Mapping[str, JSON], key: str) -> Mapping[str, JSON]:
    value = raw.get(key)
    return value if isinstance(value, dict) else {}


def _time(raw: Mapping[str, JSON], key: str) -> datetime | None:
    value = _text(raw, key)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _error(raw: Mapping[str, JSON]) -> str | None:
    """The run's error: its text, or its structure (candidates by reason) as compact JSON."""
    error = raw.get("error")
    if error is None or error == "":
        return None
    text = error if isinstance(error, str) else json.dumps(error, separators=(",", ":"))
    return text[:MAX_ERROR]


def started(raw: JSON) -> AddServerStart:
    """A 202's body: the per-run answer, or a lone run's ``{workflow_id, run_id}``."""
    if not isinstance(raw, dict):
        raise TypeError("the answer is not an object")
    if "results" not in raw:
        workflow_id = _text(raw, "workflow_id")
        if workflow_id is None:
            raise ValueError("the answer has neither results nor a workflow_id")
        return AddServerStart(1, 0, 0, (StartedRun(workflow_id, "started"),))
    results = raw["results"]
    if not isinstance(results, list):
        raise TypeError("results is not a list")
    runs: list[StartedRun] = []
    for item in results:
        if not isinstance(item, dict):
            raise TypeError("a result is not an object")
        workflow_id, status = _text(item, "workflow_id"), _text(item, "status")
        if workflow_id is None or status is None:
            raise ValueError("a result has no workflow_id or status")
        runs.append(
            StartedRun(
                workflow_id,
                status,
                server_name=_text(item, "server_name"),
                slot=_int(item, "slot"),
                error=_text(item, "error"),
            )
        )
    begun, running, failed = (_int(raw, key) for key in ("started", "already_running", "failed"))
    if begun is None or running is None or failed is None:
        raise ValueError("the answer has no counts")
    return AddServerStart(begun, running, failed, runs=tuple(runs))


def listed_runs(raw: JSON) -> list[ListedRun]:
    """``GET /workflows/runs``: workflow id, status, start and close, newest first."""
    if not isinstance(raw, list):
        raise TypeError("the run list is not a list")
    runs: list[ListedRun] = []
    for item in raw:
        if not isinstance(item, dict):
            raise TypeError("a run is not an object")
        workflow_id, status = _text(item, "workflow_id"), _text(item, "status")
        if workflow_id is None or status is None:
            raise ValueError("a run has no workflow_id or status")
        runs.append(
            ListedRun(
                workflow_id,
                run_status(status),
                started_at=_time(item, "start_time"),
                closed_at=_time(item, "close_time"),
            )
        )
    return runs


def add_server_run(raw: JSON) -> AddServerRun:
    """``GET /workflows/runs/{id}`` for an add-server run; malformed raises Type/Key/ValueError."""
    if not isinstance(raw, dict):
        raise TypeError("the run is not an object")
    workflow_id, status = _text(raw, "workflow_id"), _text(raw, "status")
    if workflow_id is None or status is None:
        raise ValueError("the run has no workflow_id or status")
    progress, result = _object(raw, "progress"), _object(raw, "result")
    return AddServerRun(
        workflow_id=workflow_id,
        status=run_status(status),
        phase=_text(progress, "phase"),
        server_name=_text(progress, "server_name") or _text(result, "server_name"),
        error=_error(raw),
    )
