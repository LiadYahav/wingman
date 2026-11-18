"""HttpScaleWorkflow: the orchestrator's update-nodepool workflow, over httpx (ADR-0062).

The workflow reads one NodePool of the cluster in day1 and on the MCE, sets
its replicas in day1 ``main``, syncs the cluster's Argo CD Application and
checks the NodePool; day1 starts a run and reads it
(``docs/notes/2026-11-16-scale-nodepools-api.md``):

- ``POST /workflows/server-lifecycle/update-nodepool`` with
  ``{mce_cluster, cluster, nodepool, replicas}`` and, on a scale-down that
  names the servers that leave, ``server_names`` (the body forbids other
  fields; ``infra_env_kind`` is refused since 2026-11-18) answers ``202
  {"workflow_id": "update-nodepool-<cluster>", "run_id"}``, 409 while a run
  of the cluster runs and while an upgrade-cluster run of it runs (its words
  say which), 422 for a body it refuses. Everything it judges later is a
  FAILED run, never a 4xx here.
- ``GET /workflows/runs/{id}`` is the run (404: none). Its ``progress`` names
  ``child_workflow_id`` while the scale-up-nodepool or scale-down-nodepool
  child runs; the child has no route of its own, so its phase is read by
  its id the same way.

Writes are never retried (ADR-0006). Refused before it was sent, a start is
``WorkflowsUnavailableError``; sent and unanswered, it may have happened:
``AmbiguousStartError``.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Final
from urllib.parse import quote

import httpx

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    ScaleAlreadyRunningError,
    ScaleRefusedError,
    WorkflowRefusedError,
    WorkflowsError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.scale import ScaleChild, ScaleRequest, ScaleRun
from wingman_day1.infrastructure.http import JSON, NOT_SENT, json_client, required_text
from wingman_day1.infrastructure.observed import Observer, Timer, WorkflowsOperation
from wingman_day1.infrastructure.provision_workflow import orchestrator_problems
from wingman_day1.infrastructure.scale_payloads import child_run, scale_run
from wingman_day1.infrastructure.workflows_api import RUNS_PATH, orchestrator_detail

SCALE_PATH: Final = "/workflows/server-lifecycle/update-nodepool"
LOOK_FIRST: Final = "Look at the cluster's scale run before trying again."
MAX_WORDS: Final = 2000
"""A 409 is shown in the orchestrator's own words: kept whole, up to this."""
_CLOSED_WITH_RESULT: Final = "completed"


class HttpScaleWorkflow:
    """A ``ScaleWorkflow`` over the orchestrator's REST API."""

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

    async def start(self, request: ScaleRequest) -> ScaleRun:
        """See ScaleWorkflow.start."""
        return await self._observer.call(
            WorkflowsOperation.START_UPDATE_NODEPOOL, self._start(request)
        )

    async def run(self, workflow_id: str) -> ScaleRun | None:
        """See ScaleWorkflow.run: the parent, then its child while the parent has no result."""
        run = await self._observer.call(WorkflowsOperation.GET_RUN, self._get(workflow_id))
        if run is None or run.child is None or run.status == _CLOSED_WITH_RESULT:
            return run
        child_id = run.child.workflow_id
        try:
            child = await self._observer.call(WorkflowsOperation.GET_RUN, self._child(child_id))
        except WorkflowsError:
            child = None  # the parent's own state still shows; the child's phase is unknown
        return dataclasses.replace(run, child=child or ScaleChild(child_id))

    # ── Internals ───────────────────────────────────────────────────────────

    async def _start(self, request: ScaleRequest) -> ScaleRun:
        cluster = request.cluster
        try:
            response = await self._client.post(SCALE_PATH, json=_start_body(request))
        except NOT_SENT as exc:
            raise WorkflowsUnavailableError(
                f"the orchestrator could not be reached to scale {cluster} "
                f"({type(exc).__name__}); nothing was started"
            ) from exc
        except httpx.TransportError as exc:
            raise AmbiguousStartError(
                f"the scale of {cluster} was sent but no answer came back "
                f"({type(exc).__name__}): it may have started. {LOOK_FIRST}"
            ) from exc
        status, detail = response.status_code, orchestrator_detail(response)
        if status == 202:
            return _started(response, cluster)
        if status == 409:
            raise ScaleAlreadyRunningError(
                _words(response) or f"{cluster} already has a scale or an upgrade running"
            )
        if status == 422:
            raise ScaleRefusedError(
                f"the orchestrator refused the scale of {cluster}; nothing was started",
                orchestrator_problems(response),
            )
        if status == 504:
            raise AmbiguousStartError(
                f"a gateway timed out waiting for the orchestrator to start the scale of "
                f"{cluster}: it may have started. {LOOK_FIRST}"
            )
        if 400 <= status < 500:
            raise WorkflowRefusedError(
                f"the orchestrator refused the scale of {cluster} ({status}){detail}"
            )
        raise WorkflowsUnavailableError(
            f"the orchestrator answered {status} to the scale of {cluster}{detail}"
        )

    async def _get(self, workflow_id: str) -> ScaleRun | None:
        raw = await self._read(workflow_id)
        if raw is None:
            return None
        try:
            return scale_run(raw)
        except (ValueError, KeyError, TypeError) as exc:
            raise WorkflowsUnavailableError(
                f"the orchestrator returned malformed run {workflow_id}"
            ) from exc

    async def _child(self, workflow_id: str) -> ScaleChild | None:
        raw = await self._read(workflow_id)
        return None if raw is None else child_run(workflow_id, raw)

    async def _read(self, workflow_id: str) -> JSON | None:
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
            return response.json()
        except ValueError as exc:
            raise WorkflowsUnavailableError(
                f"the orchestrator returned malformed run {workflow_id}"
            ) from exc


def _start_body(request: ScaleRequest) -> dict[str, JSON]:
    """The start's JSON: these four fields, one NodePool, and a scale-down's named servers."""
    body: dict[str, JSON] = {
        "mce_cluster": request.mce_cluster,
        "cluster": request.cluster,
        "nodepool": request.nodepool,
        "replicas": request.replicas,
    }
    if request.server_names:
        body["server_names"] = list(request.server_names)
    return body


def _started(response: httpx.Response, cluster: str) -> ScaleRun:
    try:
        workflow_id = required_text(response.json(), "workflow_id")
    except (ValueError, KeyError, TypeError) as exc:
        raise AmbiguousStartError(
            f"the orchestrator accepted the scale of {cluster} (202) but its answer could not "
            f"be read. {LOOK_FIRST}"
        ) from exc
    return ScaleRun(workflow_id=workflow_id, status="running")


def _words(response: httpx.Response) -> str:
    """The orchestrator's ``detail``, whole: why a run cannot start now, in its words."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return ""
    return detail.strip()[:MAX_WORDS] if isinstance(detail, str) else ""
