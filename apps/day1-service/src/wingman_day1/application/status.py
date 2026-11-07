"""Live cluster status and InfraEnvs, read from the MCE hubs (``CLUSTER_STATUS_ENABLED``).

The HostedCluster is ``openshift-<clusterName>`` in ``hcp-<clusterName>``,
where ``clusterName`` is the file's own ``clusterName`` key or, by default,
the file stem with the deployment's prefix stripped (ADR-0015). The legacy
service looked for a HostedCluster named after the full stem, which the
chart never creates.

A hub that cannot be read gives a status with ``error`` set, never an empty
healthy one.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

from wingman_day1.application.clusters import ClusterService
from wingman_day1.domain.errors import AmbiguousNameError, HubError, ResourceNotFoundError
from wingman_day1.domain.names import HostedClusterNaming, HostedClusterRef
from wingman_day1.domain.status import LiveStatus, live_status
from wingman_day1.ports import HubApi

Sleep = Callable[[float], Awaitable[None]]


class StatusService:
    """Read HostedClusters, NodePools and InfraEnvs from the hubs."""

    def __init__(
        self,
        hub: HubApi,
        clusters: ClusterService,
        *,
        naming: HostedClusterNaming,
        infraenv_namespace: str | None,
    ) -> None:
        """``infraenv_namespace`` ``None`` lists InfraEnvs across the whole hub."""
        self._hub = hub
        self._clusters = clusters
        self._naming = naming
        self._infraenv_namespace = infraenv_namespace

    async def hosted_cluster_of(self, name: str, mce: str) -> HostedClusterRef:
        """The HostedCluster a cluster file renders; derived from the name when not merged yet."""
        try:
            ref = await self._clusters.locate(name, mce=mce)
            return (await self._clusters.get(ref)).hosted_cluster
        except (ResourceNotFoundError, AmbiguousNameError):
            return self._naming.for_file(name)

    async def status(self, name: str, mce: str) -> LiveStatus:
        """One cluster's live status; hub failures land in ``error``."""
        target = await self.hosted_cluster_of(name, mce)
        try:
            hosted = await self._hub.hosted_cluster(
                mce, namespace=target.namespace, name=target.name
            )
        except HubError as exc:
            return LiveStatus(
                cluster_name=name,
                hosted_cluster=target.name,
                namespace=target.namespace,
                error=f"{type(exc).__name__.removesuffix('Error')}: {exc}",
            )
        try:
            pools = await self._hub.node_pools(mce, namespace=target.namespace)
        except HubError as exc:
            return live_status(name, hosted, [], node_pool_error=str(exc))
        return live_status(name, hosted, pools)

    async def statuses(self, clusters: Sequence[tuple[str, str]]) -> dict[str, LiveStatus]:
        """Many ``(name, mce)`` at once; every one gets an entry, failed or not."""
        results = await asyncio.gather(*(self.status(name, mce) for name, mce in clusters))
        return {status.cluster_name: status for status in results}

    async def infra_envs(self, mce: str) -> list[str]:
        """InfraEnv names on an MCE; errors propagate (the form falls back to free text)."""
        return await self._hub.infra_envs(mce, namespace=self._infraenv_namespace)

    async def watch(
        self, name: str, mce: str, *, interval: float, sleep: Sleep = asyncio.sleep
    ) -> AsyncIterator[LiveStatus]:
        """A status now and then every ``interval`` seconds, until the consumer stops."""
        while True:
            yield await self.status(name, mce)
            await sleep(interval)
