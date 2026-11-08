"""FakeHubApi: a HubApi over seeded objects, for tests.

It raises the same domain errors as ``HttpHubApi``: an MCE it does not know
is not configured, one marked unavailable fails as an unreachable hub would,
and an object that was not seeded is not found.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from wingman_day1.domain.errors import (
    HubNotConfiguredError,
    HubObjectNotFoundError,
    HubUnavailableError,
)
from wingman_day1.domain.status import HostedClusterObservation, NodePoolObservation


class FakeHubApi:
    """A ``HubApi`` whose hubs hold exactly what was seeded."""

    def __init__(
        self,
        *,
        hosted_clusters: Mapping[str, Iterable[HostedClusterObservation]] | None = None,
        node_pools: Mapping[tuple[str, str], Iterable[NodePoolObservation]] | None = None,
        infra_envs: Mapping[str, Mapping[str, Iterable[str]]] | None = None,
        mces: Iterable[str] = (),
        unavailable: Iterable[str] = (),
    ) -> None:
        """Seed the hubs.

        Args:
            hosted_clusters: Per MCE, the HostedClusters on its hub.
            node_pools: Per ``(mce, namespace)``, the NodePools there.
            infra_envs: Per MCE, InfraEnv names per namespace.
            mces: Extra MCEs that are configured but empty.
            unavailable: MCEs whose hub cannot be reached.
        """
        self._hosted_clusters = {
            (mce, hc.namespace, hc.name): hc
            for mce, clusters in (hosted_clusters or {}).items()
            for hc in clusters
        }
        self._node_pools = {key: list(pools) for key, pools in (node_pools or {}).items()}
        self._infra_envs = {
            mce: {ns: list(names) for ns, names in by_ns.items()}
            for mce, by_ns in (infra_envs or {}).items()
        }
        self._configured = (
            set(mces)
            | {mce for mce, _, _ in self._hosted_clusters}
            | {mce for mce, _ in self._node_pools}
            | set(self._infra_envs)
        )
        self._unavailable = set(unavailable)
        self._configured |= self._unavailable

    def _check(self, mce: str) -> None:
        if mce not in self._configured:
            configured = ", ".join(sorted(self._configured)) or "(none)"
            raise HubNotConfiguredError(
                f"no service-account token is configured for MCE {mce!r}; "
                f"configured MCEs: {configured}"
            )
        if mce in self._unavailable:
            raise HubUnavailableError(f"MCE {mce!r} hub API unreachable (fake)")

    async def hosted_cluster(
        self, mce: str, *, namespace: str, name: str
    ) -> HostedClusterObservation:
        """See HubApi.hosted_cluster."""
        self._check(mce)
        found = self._hosted_clusters.get((mce, namespace, name))
        if found is None:
            raise HubObjectNotFoundError(
                f"MCE {mce!r} has no HostedCluster {namespace}/{name} (404)"
            )
        return found

    async def node_pools(self, mce: str, *, namespace: str) -> list[NodePoolObservation]:
        """See HubApi.node_pools."""
        self._check(mce)
        return sorted(self._node_pools.get((mce, namespace), []), key=lambda pool: pool.name)

    async def infra_envs(self, mce: str, *, namespace: str | None) -> list[str]:
        """See HubApi.infra_envs."""
        self._check(mce)
        by_ns = self._infra_envs.get(mce, {})
        if namespace:
            return sorted(by_ns.get(namespace, []))
        return sorted(name for names in by_ns.values() for name in names)
