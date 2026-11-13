"""HttpProvisionWorkflow: the orchestrator's provision-cluster workflow, over httpx (ADR-0042).

The workflow creates a cluster: it judges the file, reserves the segment,
pushes the file on its own branch, opens the merge request, waits for a
person to merge it and registers the cluster in day2. Day1 starts a run and
reads how it is going:

- ``POST /workflows/cluster-lifecycle/provision-cluster?cluster=&mce=`` with
  the cluster file as an ``application/yaml`` body answers ``202
  {"workflow_id", "run_id"}``, 409 while a run for the cluster is going and
  422 for a name or body it cannot use. Everything it judges after the start
  is a FAILED run, never a 4xx here.
- ``GET /workflows/runs/{id}`` is one run: ``progress.phase``,
  ``progress.merge_request_url`` and ``progress.merge_request_state`` while
  it runs (and where a failure stopped it), ``error`` once failed (404: none).

A start is a write and is never retried (ADR-0006). Refused before it was
sent (no connection), it is ``WorkflowsUnavailableError``; sent and
unanswered, ``AmbiguousStartError``: the run may exist.
"""

from __future__ import annotations

import time
from typing import Final
from urllib.parse import quote

import httpx

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    ProvisionAlreadyRunningError,
    ProvisionRefusedError,
    WorkflowRefusedError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.servers import run_status
from wingman_day1.domain.workflows import ProvisionRun
from wingman_day1.infrastructure.http import JSON, NOT_SENT, json_client
from wingman_day1.infrastructure.observed import Observer, Timer, WorkflowsOperation
from wingman_day1.infrastructure.workflows_api import RUNS_PATH, orchestrator_detail

START_PATH: Final = "/workflows/cluster-lifecycle/provision-cluster"
CHECK_FIRST: Final = "Look at the cluster's provision run before starting it again."
MAX_PROBLEMS: Final = 10


class HttpProvisionWorkflow:
    """A ``ProvisionWorkflow`` over the orchestrator's REST API."""

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
            base_url=base_url,
            verify=verify,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def start(self, *, cluster: str, mce: str, content: str) -> ProvisionRun:
        """See ProvisionWorkflow.start."""
        return await self._observer.call(
            WorkflowsOperation.START_PROVISION,
            self._start(cluster=cluster, mce=mce, content=content),
        )

    async def run(self, workflow_id: str) -> ProvisionRun | None:
        """See ProvisionWorkflow.run."""
        return await self._observer.call(WorkflowsOperation.GET_RUN, self._run(workflow_id))

    async def _start(self, *, cluster: str, mce: str, content: str) -> ProvisionRun:
        try:
            response = await self._client.post(
                START_PATH,
                params={"cluster": cluster, "mce": mce},
                content=content.encode("utf-8"),
                headers={"Content-Type": "application/yaml"},
            )
        except NOT_SENT as exc:
            raise WorkflowsUnavailableError(
                f"the orchestrator could not be reached to provision {cluster} "
                f"({type(exc).__name__}); nothing was started"
            ) from exc
        except httpx.TransportError as exc:
            raise AmbiguousStartError(
                f"the provision of {cluster} was sent but no answer came back "
                f"({type(exc).__name__}): it may have started. {CHECK_FIRST}"
            ) from exc
        status = response.status_code
        if status == 202:
            return _started(response, cluster)
        if status == 409:
            raise ProvisionAlreadyRunningError(
                f"a provision run for {cluster} is already going{orchestrator_detail(response)}"
            )
        if status == 422:
            raise ProvisionRefusedError(
                f"the orchestrator refused to provision {cluster}", orchestrator_problems(response)
            )
        if status == 504:
            raise AmbiguousStartError(
                f"a gateway timed out waiting for the orchestrator to start the provision of "
                f"{cluster}: it may have started. {CHECK_FIRST}"
            )
        detail = orchestrator_detail(response)
        if 400 <= status < 500:
            raise WorkflowRefusedError(
                f"the orchestrator refused the provision of {cluster} ({status}){detail}"
            )
        raise WorkflowsUnavailableError(
            f"the orchestrator answered {status} to the provision of {cluster}{detail}"
        )

    async def _run(self, workflow_id: str) -> ProvisionRun | None:
        what = f"reading run {workflow_id}"
        try:
            response = await self._client.get(f"{RUNS_PATH}/{quote(workflow_id, safe='')}")
        except httpx.TransportError as exc:
            raise WorkflowsUnavailableError(
                f"the orchestrator is unreachable {what}: {type(exc).__name__}"
            ) from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise WorkflowsUnavailableError(
                f"the orchestrator answered {response.status_code} {what}"
            )
        try:
            return provision_run(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise WorkflowsUnavailableError(
                f"the orchestrator returned a malformed run {workflow_id}"
            ) from exc


def _started(response: httpx.Response, cluster: str) -> ProvisionRun:
    try:
        raw = response.json()
        workflow_id = raw["workflow_id"]
        if not isinstance(workflow_id, str) or not workflow_id:
            raise ValueError("workflow_id is not a non-empty string")
    except (ValueError, KeyError, TypeError) as exc:
        raise AmbiguousStartError(
            f"the orchestrator accepted the provision of {cluster} (202) but its answer could "
            f"not be read. {CHECK_FIRST}"
        ) from exc
    return ProvisionRun(workflow_id=workflow_id, status="running")


def _text(raw: dict[str, JSON], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) and value else None


def provision_run(raw: JSON) -> ProvisionRun:
    """``GET /workflows/runs/{id}`` for a provision run; malformed raises Type/Key/ValueError."""
    if not isinstance(raw, dict):
        raise TypeError("the run is not an object")
    workflow_id, status = raw["workflow_id"], raw["status"]
    if not (isinstance(workflow_id, str) and workflow_id and isinstance(status, str)):
        raise ValueError("the run has no workflow_id or status")
    progress = raw.get("progress")
    progress = progress if isinstance(progress, dict) else {}
    result = raw.get("result")
    result = result if isinstance(result, dict) else {}
    return ProvisionRun(
        workflow_id=workflow_id,
        status=run_status(status),
        phase=_text(progress, "phase"),
        error=_text(raw, "error"),
        merge_request_url=_text(progress, "merge_request_url")
        or _text(result, "merge_request_url"),
        merge_request_state=_text(progress, "merge_request_state"),
    )


def orchestrator_problems(response: httpx.Response) -> list[str]:
    """The orchestrator's 422 detail, one line per finding (FastAPI's list, or its text)."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return []
    if isinstance(detail, str) and detail.strip():
        return [detail.strip()]
    if not isinstance(detail, list):
        return []
    problems: list[str] = []
    for item in detail[:MAX_PROBLEMS]:
        if not isinstance(item, dict):
            continue
        where = ".".join(str(part) for part in item.get("loc", []) if part not in ("query", "body"))
        message = item.get("msg")
        if isinstance(message, str) and message:
            problems.append(f"{where}: {message}" if where else message)
    return problems
