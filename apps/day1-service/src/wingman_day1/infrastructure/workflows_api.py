"""HttpUninstallWorkflow: the orchestrator's uninstall-server-from-hc workflow, over httpx.

The workflow owns the procedure (drain, lock, removal, and the checks before
them). Day1 starts a run and reads how it is going (ADR-0038):

- ``POST /workflows/server-lifecycle/uninstall-server-from-hc`` with
  ``{"server_names": "<one name>", "mce_cluster": ..., "namespace"?: ...}``
  answers ``202 {"workflow_id", "run_id"}``, 409 while that server is
  uninstalling, 422 for a body it refuses and 502 when Temporal refuses.
  Every refusal after the start is a FAILED run, never a 4xx here.
- ``GET /workflows/runs?workflow_type=UninstallServerFromHcWorkflow&limit=200``
  lists the newest runs of the fleet; ``GET /workflows/runs/{id}`` is one run,
  with ``progress.phase`` while it runs and after a failure (404: no run).

The orchestrator has no auth and no ``requested_by`` field: day1 logs who
started a run. A start is a write and is never retried (ADR-0006). Refused
before it was sent (no connection), it is ``WorkflowsUnavailableError``; sent
and unanswered (a read timeout, a dropped connection, a gateway's 504), it
is ``AmbiguousStartError``: the run may exist.
"""

from __future__ import annotations

import ssl
import time
from typing import Any, Final
from urllib.parse import quote

import httpx

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    UninstallAlreadyRunningError,
    WorkflowRefusedError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.servers import RunSummary, run_status
from wingman_day1.domain.workflows import WorkflowRun
from wingman_day1.infrastructure.observed import Observer, Timer, WorkflowsOperation

JSON = Any
"""A decoded JSON value; narrowed where it is read."""

START_PATH: Final = "/workflows/server-lifecycle/uninstall-server-from-hc"
RUNS_PATH: Final = "/workflows/runs"
WORKFLOW_TYPE: Final = "UninstallServerFromHcWorkflow"
"""The Temporal class name the run list filters on (it answers ``[]`` for any other name)."""
RUNS_LIMIT: Final = 200
"""The most the run list returns; it has no cursor."""
NOT_SENT: Final = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
"""Transport errors that happen before a request leaves: nothing reached the orchestrator."""
MAX_DETAIL: Final = 300
CHECK_FIRST: Final = "Look at the node's uninstall run before trying again."


class HttpUninstallWorkflow:
    """An ``UninstallWorkflow`` over the orchestrator's REST API."""

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
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            verify=verify
            if isinstance(verify, bool)
            else ssl.create_default_context(cafile=verify),
            transport=transport,
            headers={"Accept": "application/json"},
        )

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def runs(self) -> list[RunSummary]:
        """See UninstallWorkflow.runs."""
        return await self._observer.call(WorkflowsOperation.LIST_RUNS, self._runs())

    async def run(self, workflow_id: str) -> WorkflowRun | None:
        """See UninstallWorkflow.run."""
        return await self._observer.call(WorkflowsOperation.GET_RUN, self._run(workflow_id))

    async def start(self, *, server_name: str, mce: str, namespace: str | None) -> WorkflowRun:
        """See UninstallWorkflow.start."""
        return await self._observer.call(
            WorkflowsOperation.START_UNINSTALL,
            self._start(server_name=server_name, mce=mce, namespace=namespace),
        )

    async def _runs(self) -> list[RunSummary]:
        response = await self._read(
            RUNS_PATH,
            what="listing uninstall runs",
            params={"workflow_type": WORKFLOW_TYPE, "limit": RUNS_LIMIT},
        )
        if response.status_code != 200:
            raise WorkflowsUnavailableError(
                f"the orchestrator answered {response.status_code} listing uninstall runs"
            )
        try:
            return _summaries(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise WorkflowsUnavailableError(
                "the orchestrator returned a malformed run list"
            ) from exc

    async def _run(self, workflow_id: str) -> WorkflowRun | None:
        what = f"reading run {workflow_id}"
        response = await self._read(f"{RUNS_PATH}/{quote(workflow_id, safe='')}", what=what)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise WorkflowsUnavailableError(
                f"the orchestrator answered {response.status_code} {what}"
            )
        try:
            return _run(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise WorkflowsUnavailableError(
                f"the orchestrator returned a malformed run {workflow_id}"
            ) from exc

    async def _read(
        self, path: str, *, what: str, params: dict[str, str | int] | None = None
    ) -> httpx.Response:
        try:
            return await self._client.get(path, params=params)
        except httpx.TransportError as exc:
            raise WorkflowsUnavailableError(
                f"the orchestrator is unreachable {what}: {type(exc).__name__}"
            ) from exc

    async def _start(self, *, server_name: str, mce: str, namespace: str | None) -> WorkflowRun:
        body: dict[str, str] = {"server_names": server_name, "mce_cluster": mce}
        if namespace:
            body["namespace"] = namespace
        try:
            response = await self._client.post(START_PATH, json=body)
        except NOT_SENT as exc:
            raise WorkflowsUnavailableError(
                f"the orchestrator could not be reached to uninstall {server_name} "
                f"({type(exc).__name__}); nothing was started"
            ) from exc
        except httpx.TransportError as exc:
            raise AmbiguousStartError(
                f"the uninstall of {server_name} was sent but no answer came back "
                f"({type(exc).__name__}): it may have started. {CHECK_FIRST}"
            ) from exc
        status = response.status_code
        if status == 202:
            return _started(response, server_name)
        if status == 409:
            raise UninstallAlreadyRunningError(f"an uninstall of {server_name} is already running")
        if status == 504:
            raise AmbiguousStartError(
                f"a gateway timed out waiting for the orchestrator to start the uninstall of "
                f"{server_name}: it may have started. {CHECK_FIRST}"
            )
        detail = _detail(response)
        if 400 <= status < 500:
            raise WorkflowRefusedError(
                f"the orchestrator refused the uninstall of {server_name} ({status}){detail}"
            )
        raise WorkflowsUnavailableError(
            f"the orchestrator answered {status} to the uninstall of {server_name}{detail}"
        )


def _started(response: httpx.Response, server_name: str) -> WorkflowRun:
    try:
        raw = response.json()
        workflow_id = raw["workflow_id"]
        if not isinstance(workflow_id, str) or not workflow_id:
            raise ValueError("workflow_id is not a non-empty string")
    except (ValueError, KeyError, TypeError) as exc:
        raise AmbiguousStartError(
            f"the orchestrator accepted the uninstall of {server_name} (202) but its answer "
            f"could not be read. {CHECK_FIRST}"
        ) from exc
    return WorkflowRun(workflow_id=workflow_id, status="running")


def _summaries(raw: JSON) -> list[RunSummary]:
    if not isinstance(raw, list):
        raise TypeError("the run list is not a list")
    summaries: list[RunSummary] = []
    for item in raw:
        if not isinstance(item, dict):
            raise TypeError("a run is not an object")
        workflow_id, status = item["workflow_id"], item["status"]
        if not (isinstance(workflow_id, str) and workflow_id and isinstance(status, str)):
            raise ValueError("a run has no workflow_id or status")
        summaries.append(RunSummary(workflow_id=workflow_id, status=run_status(status)))
    return summaries


def _run(raw: JSON) -> WorkflowRun:
    if not isinstance(raw, dict):
        raise TypeError("the run is not an object")
    workflow_id, status = raw["workflow_id"], raw["status"]
    if not (isinstance(workflow_id, str) and workflow_id and isinstance(status, str)):
        raise ValueError("the run has no workflow_id or status")
    progress = raw.get("progress")
    phase = progress.get("phase") if isinstance(progress, dict) else None
    error = raw.get("error")
    return WorkflowRun(
        workflow_id=workflow_id,
        status=run_status(status),
        phase=phase if isinstance(phase, str) and phase else None,
        error=error if isinstance(error, str) and error else None,
    )


def _detail(response: httpx.Response) -> str:
    """The orchestrator's own ``detail``, when it is text, as ``": <detail>"``."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return ""
    if not isinstance(detail, str) or not detail.strip():
        return ""
    return f": {detail.strip()[:MAX_DETAIL]}"
