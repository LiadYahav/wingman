"""The update-nodepool workflow's port (ADR-0062), re-exported from ``wingman_day1.ports``."""

from __future__ import annotations

from typing import Protocol

from wingman_day1.domain.scale import ScaleRequest, ScaleRun


class ScaleWorkflow(Protocol):
    """The orchestrator's ``update-nodepool`` workflow (ADR-0062).

    The workflow plans the replicas, commits them to day1 ``main``, syncs the
    cluster's Argo CD Application and checks the NodePools; Wingman starts a
    run and reads it. A start is never retried (ADR-0006). Reads raise
    ``WorkflowsUnavailableError``.
    """

    async def start(self, request: ScaleRequest) -> ScaleRun:
        """Start one run for ``request.cluster``.

        Raises ``ScaleAlreadyRunningError`` for the orchestrator's 409 (a run
        of the cluster, or an upgrade-cluster run of it, is running),
        ``ScaleRefusedError`` for its 422, ``WorkflowsUnavailableError`` when
        nothing was started, and ``AmbiguousStartError`` when it was sent but
        the answer was lost.
        """
        ...

    async def run(self, workflow_id: str) -> ScaleRun | None:
        """The run, with its child's phase while the child runs; ``None`` when there is none."""
        ...
