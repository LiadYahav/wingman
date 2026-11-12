"""CachedHubApi: an MCE hub's reads, cached for a few seconds per replica.

A cluster's nodes are six reads of its MCE (ADR-0038), and live status two
per cluster on every open cluster list (ADR-0041). Both are polled, by every
person with a page open, so the reads are cached for a short TTL (ADR-0011)
and shared. A failure is not cached.
"""

from __future__ import annotations

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.machines import (
    AgentMachineObservation,
    AgentObservation,
    MachineObservation,
    MachineSetObservation,
)
from wingman_day1.domain.status import HostedClusterObservation, NodePoolObservation
from wingman_day1.infrastructure import cache_keys as keys
from wingman_day1.ports import HubApi


class CachedHubApi:
    """A ``HubApi`` that caches ``inner``'s reads."""

    def __init__(self, inner: HubApi, cache: TtlCache, *, ttl: float) -> None:
        """Cache ``inner``'s reads in ``cache`` for ``ttl`` seconds."""
        self._inner = inner
        self._cache = cache
        self._ttl = ttl

    async def hosted_cluster(
        self, mce: str, *, namespace: str, name: str
    ) -> HostedClusterObservation:
        """See HubApi.hosted_cluster."""
        return await self._cache.get_or_fetch(
            keys.hub(mce, "hostedcluster", namespace, name),
            lambda: self._inner.hosted_cluster(mce, namespace=namespace, name=name),
            ttl=self._ttl,
        )

    async def node_pools(self, mce: str, *, namespace: str) -> list[NodePoolObservation]:
        """See HubApi.node_pools."""
        return await self._cache.get_or_fetch(
            keys.hub(mce, "nodepools", namespace),
            lambda: self._inner.node_pools(mce, namespace=namespace),
            ttl=self._ttl,
        )

    async def infra_envs(self, mce: str, *, namespace: str | None) -> list[str]:
        """See HubApi.infra_envs."""
        return await self._cache.get_or_fetch(
            keys.hub(mce, "infraenvs", namespace or "*"),
            lambda: self._inner.infra_envs(mce, namespace=namespace),
            ttl=self._ttl,
        )

    async def machines(self, mce: str, *, namespace: str) -> list[MachineObservation]:
        """See HubApi.machines."""
        return await self._cache.get_or_fetch(
            keys.hub(mce, "machines", namespace),
            lambda: self._inner.machines(mce, namespace=namespace),
            ttl=self._ttl,
        )

    async def machine_sets(self, mce: str, *, namespace: str) -> list[MachineSetObservation]:
        """See HubApi.machine_sets."""
        return await self._cache.get_or_fetch(
            keys.hub(mce, "machinesets", namespace),
            lambda: self._inner.machine_sets(mce, namespace=namespace),
            ttl=self._ttl,
        )

    async def agent_machines(self, mce: str, *, namespace: str) -> list[AgentMachineObservation]:
        """See HubApi.agent_machines."""
        return await self._cache.get_or_fetch(
            keys.hub(mce, "agentmachines", namespace),
            lambda: self._inner.agent_machines(mce, namespace=namespace),
            ttl=self._ttl,
        )

    async def agents(self, mce: str, *, namespace: str) -> list[AgentObservation]:
        """See HubApi.agents."""
        return await self._cache.get_or_fetch(
            keys.hub(mce, "agents", namespace),
            lambda: self._inner.agents(mce, namespace=namespace),
            ttl=self._ttl,
        )
