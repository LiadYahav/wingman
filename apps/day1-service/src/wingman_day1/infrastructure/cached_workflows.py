"""CachedUninstallWorkflow: the orchestrator's uninstall runs, cached for a few seconds.

A cluster's nodes need the fleet's newest runs (one list) and, for the nodes
that have one, the run itself (its step and error). Both are cached for a
short TTL per replica (ADR-0011). Starting a run clears them all, whatever
the answer, so the next read sees the run if it exists. A failure is not
cached.
"""

from __future__ import annotations

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.servers import RunSummary
from wingman_day1.domain.workflows import WorkflowRun
from wingman_day1.infrastructure import cache_keys as keys
from wingman_day1.ports import UninstallWorkflow


class CachedUninstallWorkflow:
    """An ``UninstallWorkflow`` that caches ``inner``'s reads and forgets them on a start."""

    def __init__(self, inner: UninstallWorkflow, cache: TtlCache, *, ttl: float) -> None:
        """Cache ``inner``'s reads in ``cache`` for ``ttl`` seconds."""
        self._inner = inner
        self._cache = cache
        self._ttl = ttl

    async def runs(self) -> list[RunSummary]:
        """See UninstallWorkflow.runs."""
        return list(
            await self._cache.get_or_fetch(keys.uninstall_runs(), self._inner.runs, ttl=self._ttl)
        )

    async def run(self, workflow_id: str) -> WorkflowRun | None:
        """See UninstallWorkflow.run."""
        return await self._cache.get_or_fetch(
            keys.uninstall_run(workflow_id), lambda: self._inner.run(workflow_id), ttl=self._ttl
        )

    async def start(self, *, server_name: str, mce: str, namespace: str | None) -> WorkflowRun:
        """See UninstallWorkflow.start: never retried; the cached runs are dropped after it."""
        try:
            return await self._inner.start(server_name=server_name, mce=mce, namespace=namespace)
        finally:
            self._cache.invalidate_prefix(keys.uninstall_runs_prefix())
