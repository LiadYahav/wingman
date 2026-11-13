"""The orchestrator's uninstall, add-server and upgrade runs, cached for a few seconds.

A cluster's nodes need the fleet's newest uninstall runs (one list) and, for
the nodes that have one, the run itself (its step and error); Inventory
Management the newest add-server runs and their phases (ADR-0057); the
Clusters page's Upgrades view the newest upgrade runs (ADR-0055). All are
cached for a short TTL per replica (ADR-0011). Starting a run clears that
workflow's reads, whatever the answer, so the next read sees the run if it
exists. A failure is not cached.
"""

from __future__ import annotations

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.add_server import AddServerRequest, AddServerRun, AddServerStart, ListedRun
from wingman_day1.domain.servers import RunSummary
from wingman_day1.domain.upgrades import UpgradeDecision, UpgradeRequest, UpgradeRun, UpgradeTargets
from wingman_day1.domain.workflows import WorkflowRun
from wingman_day1.infrastructure import cache_keys as keys
from wingman_day1.ports import AddServerWorkflow, UninstallWorkflow, UpgradeWorkflow


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


class CachedUpgradeWorkflow:
    """An ``UpgradeWorkflow`` for the fleet's list: its reads cached, forgotten on any write.

    The list reads the run list and the first runs by id on every page's
    poll; a short cache keeps that to one read per TTL. A cluster's own
    Upgrade panel reads its run uncached (ADR-0055's amendment).
    """

    def __init__(self, inner: UpgradeWorkflow, cache: TtlCache, *, ttl: float) -> None:
        """Cache ``inner``'s reads in ``cache`` for ``ttl`` seconds."""
        self._inner = inner
        self._cache = cache
        self._ttl = ttl

    async def runs(self) -> list[ListedRun]:
        """See UpgradeWorkflow.runs."""
        return list(
            await self._cache.get_or_fetch(keys.upgrade_runs(), self._inner.runs, ttl=self._ttl)
        )

    async def run(self, workflow_id: str) -> UpgradeRun | None:
        """See UpgradeWorkflow.run."""
        return await self._cache.get_or_fetch(
            keys.upgrade_run(workflow_id), lambda: self._inner.run(workflow_id), ttl=self._ttl
        )

    async def targets(self, cluster: str) -> UpgradeTargets:
        """See UpgradeWorkflow.targets: not cached."""
        return await self._inner.targets(cluster)

    async def start(self, request: UpgradeRequest) -> UpgradeRun:
        """See UpgradeWorkflow.start: never retried; the cached runs are dropped after it."""
        try:
            return await self._inner.start(request)
        finally:
            self._cache.invalidate_prefix(keys.upgrade_runs_prefix())

    async def decide(
        self,
        workflow_id: str,
        decision: UpgradeDecision,
        *,
        by: str,
        reason: str | None = None,
        nodepool: str | None = None,
    ) -> None:
        """See UpgradeWorkflow.decide: never retried; the cached runs are dropped after it."""
        try:
            await self._inner.decide(workflow_id, decision, by=by, reason=reason, nodepool=nodepool)
        finally:
            self._cache.invalidate_prefix(keys.upgrade_runs_prefix())

    async def decide_action(
        self, workflow_id: str, action_id: str, *, approve: bool, by: str
    ) -> None:
        """See UpgradeWorkflow.decide_action: the cached runs are dropped after it."""
        try:
            await self._inner.decide_action(workflow_id, action_id, approve=approve, by=by)
        finally:
            self._cache.invalidate_prefix(keys.upgrade_runs_prefix())


class CachedAddServerWorkflow:
    """An ``AddServerWorkflow`` that caches ``inner``'s reads and forgets them on a start."""

    def __init__(self, inner: AddServerWorkflow, cache: TtlCache, *, ttl: float) -> None:
        """Cache ``inner``'s reads in ``cache`` for ``ttl`` seconds."""
        self._inner = inner
        self._cache = cache
        self._ttl = ttl

    async def runs(self) -> list[ListedRun]:
        """See AddServerWorkflow.runs."""
        return list(
            await self._cache.get_or_fetch(keys.add_server_runs(), self._inner.runs, ttl=self._ttl)
        )

    async def run(self, workflow_id: str) -> AddServerRun | None:
        """See AddServerWorkflow.run."""
        return await self._cache.get_or_fetch(
            keys.add_server_run(workflow_id), lambda: self._inner.run(workflow_id), ttl=self._ttl
        )

    async def start(self, request: AddServerRequest) -> AddServerStart:
        """See AddServerWorkflow.start: never retried; the cached runs are dropped after it."""
        try:
            return await self._inner.start(request)
        finally:
            self._cache.invalidate_prefix(keys.add_server_runs_prefix())
