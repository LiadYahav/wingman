"""FakeProvisionWorkflow: the provision-cluster workflow in memory (ADR-0042).

Tests seed and drive it directly; ``DAY1_FAKE_FLEET=true`` (development only)
uses it so the local demo can start runs. A run walks a few sample phases on
the injected clock and then waits for its merge request, as the real one
waits for a person. The phases are a sample for the demo, nothing more: day1
passes the real workflow's phases through and keeps no list of them. A
second start while one runs answers like the orchestrator's 409, and a file
without a ``mastertag`` fails its run, as the real one's checks do: refusals
happen inside the run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from wingman_core.ports.clock import Clock, system_clock
from wingman_day1.domain.errors import (
    Day1Error,
    ProvisionAlreadyRunningError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.names import HOSTED_CLUSTER_PREFIX
from wingman_day1.domain.workflows import ProvisionRun, provision_workflow_id

DEMO_PHASES: Final = (
    "inspecting-target",
    "allocating-segment",
    "publishing-cluster-file",
    "opening-merge-request",
    "awaiting-merge",
)
"""A few of the real workflow's steps, for the demo only."""
PHASE_SECONDS: Final = 6.0
MERGE_REQUESTS: Final = "https://gitlab.example/gitops-day1/platform-config/-/merge_requests"
"""Where the fake's merge requests point: an example host, never a real one."""


@dataclass(slots=True)
class _Run:
    workflow_id: str
    started: datetime
    number: int
    status: str = "running"
    phase: str | None = None
    error: str | None = None


class FakeProvisionWorkflow:
    """A ``ProvisionWorkflow`` whose runs walk the demo phases and then wait for their merge."""

    def __init__(self, *, clock: Clock = system_clock, unavailable: bool = False) -> None:
        """Start runs on ``clock``; ``unavailable`` fails every call, as if it were down."""
        self._clock = clock
        self._runs: dict[str, _Run] = {}
        self.unavailable = unavailable
        self.fail_start: Day1Error | None = None
        """When set, ``start`` raises it (an ambiguous or refused start, for tests)."""
        self.starts: list[dict[str, str]] = []
        """Every start's input, in order."""

    async def start(self, *, cluster: str, mce: str, content: str) -> ProvisionRun:
        """See ProvisionWorkflow.start."""
        self._check()
        self.starts.append({"cluster": cluster, "mce": mce, "content": content})
        if self.fail_start is not None:
            raise self.fail_start
        stem = (
            cluster
            if cluster.startswith(HOSTED_CLUSTER_PREFIX)
            else f"{HOSTED_CLUSTER_PREFIX}{cluster}"
        )
        workflow_id = provision_workflow_id(stem)
        running = self._runs.get(workflow_id)
        if running is not None and running.status == "running":
            raise ProvisionAlreadyRunningError(
                f"a provision run for {cluster} is already going: {workflow_id}"
            )
        run = _Run(workflow_id, self._clock(), number=len(self._runs) + 1, phase=DEMO_PHASES[0])
        if "mastertag" not in content:
            run.status = "failed"
            run.error = "ClusterValuesRejectedError: the file has no mastertag (fake)"
        self._runs[workflow_id] = run
        return ProvisionRun(workflow_id, "running")

    async def run(self, workflow_id: str) -> ProvisionRun | None:
        """See ProvisionWorkflow.run."""
        self._check()
        run = self._runs.get(workflow_id)
        if run is None:
            return None
        opened = run.phase in DEMO_PHASES[DEMO_PHASES.index("opening-merge-request") :]
        return ProvisionRun(
            run.workflow_id,
            run.status,
            phase=run.phase,
            error=run.error,
            merge_request_url=f"{MERGE_REQUESTS}/{100 + run.number}" if opened else None,
            merge_request_state="opened" if opened else None,
        )

    def _check(self) -> None:
        if self.unavailable:
            raise WorkflowsUnavailableError("the orchestrator is unreachable (fake)")
        now = self._clock()
        for run in self._runs.values():
            if run.status != "running":
                continue
            step = int((now - run.started).total_seconds() // PHASE_SECONDS)
            run.phase = DEMO_PHASES[min(step, len(DEMO_PHASES) - 1)]
