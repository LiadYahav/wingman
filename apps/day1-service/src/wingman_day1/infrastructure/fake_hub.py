"""FakeHubApi: a HubApi over seeded objects, for tests and the fake fleet.

It raises the same domain errors as ``HttpHubApi``: an MCE it does not know
is not configured, one marked unavailable fails as an unreachable hub would,
one marked denied refuses the token, and an object that was not seeded is
not found (a list that was not seeded is empty, as a namespace without
objects lists on a real hub). Each hub's own nodes and its pods per node are
seeded per MCE (placement's free pods, ADR-0050).

``remove_server`` is what a completed uninstall leaves on a real MCE: the
server's Agent, AgentMachine and Machine are gone, and the NodePool's
MachineSet creates a replacement Machine that waits for a free Agent.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Mapping, Sequence

from wingman_day1.domain.errors import (
    HubDeniedError,
    HubNotConfiguredError,
    HubObjectNotFoundError,
    HubUnavailableError,
)
from wingman_day1.domain.machines import (
    INFRA_ENV_LABEL,
    AgentMachineObservation,
    AgentObservation,
    MachineObservation,
    MachineSetObservation,
)
from wingman_day1.domain.mce_capacity import NodeObservation
from wingman_day1.domain.status import Condition, HostedClusterObservation, NodePoolObservation

Key = tuple[str, str]
"""``(mce, namespace)``."""
NO_SUITABLE_AGENTS = Condition("AgentReserved", "False", "NoSuitableAgents", "")
FREE_AGENT = (
    Condition("Bound", "False", "Unbound", ""),
    Condition("Connected", "True", "AgentIsConnected", ""),
    Condition("Validated", "True", "ValidationsPassing", ""),
)
"""An Agent the provider would take: approved, connected, validated, bound to nothing."""


class FakeHubApi:
    """A ``HubApi`` whose hubs hold exactly what was seeded."""

    def __init__(
        self,
        *,
        hosted_clusters: Mapping[str, Iterable[HostedClusterObservation]] | None = None,
        node_pools: Mapping[Key, Iterable[NodePoolObservation]] | None = None,
        infra_envs: Mapping[str, Mapping[str, Iterable[str]]] | None = None,
        machines: Mapping[Key, Iterable[MachineObservation]] | None = None,
        machine_sets: Mapping[Key, Iterable[MachineSetObservation]] | None = None,
        agent_machines: Mapping[Key, Iterable[AgentMachineObservation]] | None = None,
        agents: Mapping[Key, Iterable[AgentObservation]] | None = None,
        nodes: Mapping[str, Iterable[NodeObservation]] | None = None,
        pods: Mapping[str, Mapping[str, int]] | None = None,
        mces: Iterable[str] = (),
        unavailable: Iterable[str] = (),
        denied: Iterable[str] = (),
        free_of_any_type: Mapping[str, int] | None = None,
    ) -> None:
        """Seed the hubs.

        Args:
            hosted_clusters: Per MCE, the HostedClusters on its hub.
            node_pools: Per ``(mce, namespace)``, the NodePools there.
            infra_envs: Per MCE, InfraEnv names per namespace.
            machines: Per ``(mce, control-plane namespace)``, the Machines there.
            machine_sets: Per ``(mce, control-plane namespace)``, the MachineSets.
            agent_machines: Per ``(mce, control-plane namespace)``, the AgentMachines.
            agents: Per ``(mce, agent namespace)``, the Agents.
            nodes: Per MCE, the hub's own nodes.
            pods: Per MCE, the non-terminal pods on each of its nodes.
            mces: Extra MCEs that are configured but empty.
            unavailable: MCEs whose hub cannot be reached.
            denied: MCEs whose hub refuses Wingman's token (403).
            free_of_any_type: Per MCE, how many free Agents it has of any InfraEnv
                asked for (a hub with room for every node type, for tests).
        """
        self._hosted_clusters = {
            (mce, hc.namespace, hc.name): hc
            for mce, clusters in (hosted_clusters or {}).items()
            for hc in clusters
        }
        self._node_pools = _lists(node_pools)
        self._infra_envs = {
            mce: {ns: list(names) for ns, names in by_ns.items()}
            for mce, by_ns in (infra_envs or {}).items()
        }
        self._machines = _lists(machines)
        self._machine_sets = _lists(machine_sets)
        self._agent_machines = _lists(agent_machines)
        self._agents = _lists(agents)
        self._nodes = {mce: list(found) for mce, found in (nodes or {}).items()}
        self._pods = {mce: dict(counts) for mce, counts in (pods or {}).items()}
        keyed = (self._node_pools, self._machines, self._machine_sets, self._agent_machines)
        self._configured = (
            set(mces)
            | {mce for mce, _, _ in self._hosted_clusters}
            | {mce for table in (*keyed, self._agents) for mce, _ in table}
            | set(self._infra_envs)
            | set(self._nodes)
            | set(self._pods)
        )
        self._unavailable = set(unavailable)
        self._denied = set(denied)
        self._free_of_any_type = dict(free_of_any_type or {})
        self._configured |= set(self._free_of_any_type)
        self._configured |= self._unavailable | self._denied
        self._backfills = itertools.count(1)

    def _check(self, mce: str) -> None:
        if mce not in self._configured:
            configured = ", ".join(sorted(self._configured)) or "(none)"
            raise HubNotConfiguredError(
                f"no service-account token is configured for MCE {mce!r}; "
                f"configured MCEs: {configured}"
            )
        if mce in self._unavailable:
            raise HubUnavailableError(f"MCE {mce!r} hub API unreachable (fake)")
        if mce in self._denied:
            raise HubDeniedError(f"MCE {mce!r} hub API denied Wingman's token (403) (fake)")

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

    async def machines(self, mce: str, *, namespace: str) -> list[MachineObservation]:
        """See HubApi.machines."""
        self._check(mce)
        return sorted(self._machines.get((mce, namespace), []), key=lambda m: m.name)

    async def machine_sets(self, mce: str, *, namespace: str) -> list[MachineSetObservation]:
        """See HubApi.machine_sets."""
        self._check(mce)
        return sorted(self._machine_sets.get((mce, namespace), []), key=lambda s: s.name)

    async def agent_machines(self, mce: str, *, namespace: str) -> list[AgentMachineObservation]:
        """See HubApi.agent_machines."""
        self._check(mce)
        return sorted(self._agent_machines.get((mce, namespace), []), key=lambda a: a.name)

    async def agents(self, mce: str, *, namespace: str) -> list[AgentObservation]:
        """See HubApi.agents."""
        self._check(mce)
        return sorted(self._agents.get((mce, namespace), []), key=lambda a: a.name)

    async def nodes(self, mce: str) -> list[NodeObservation]:
        """See HubApi.nodes."""
        self._check(mce)
        return sorted(self._nodes.get(mce, []), key=lambda node: node.name)

    async def infra_env_agents(
        self, mce: str, *, infra_envs: Sequence[str], namespace: str | None
    ) -> list[AgentObservation]:
        """See HubApi.infra_env_agents."""
        self._check(mce)
        wanted = set(infra_envs)
        seeded = [
            agent
            for (agent_mce, agent_ns), agents in self._agents.items()
            if agent_mce == mce and (namespace is None or agent_ns == namespace)
            for agent in agents
            if agent.infra_env in wanted
        ]
        roomy = [
            AgentObservation(
                name=f"{infra_env}-free-{i}",
                labels={INFRA_ENV_LABEL: infra_env},
                approved=True,
                conditions=FREE_AGENT,
            )
            for infra_env in sorted(wanted)
            for i in range(self._free_of_any_type.get(mce, 0))
        ]
        return sorted([*seeded, *roomy], key=lambda agent: agent.name)

    async def pods_per_node(self, mce: str) -> dict[str, int]:
        """See HubApi.pods_per_node."""
        self._check(mce)
        return dict(self._pods.get(mce, {}))

    def remove_server(self, server_name: str) -> bool:
        """Remove the Agent, AgentMachine and Machine of a server, and backfill its Machine.

        The server is found by its Agent's BareMetalHost label (ignoring case).
        Returns whether anything was removed.
        """
        for (mce, _), agents in self._agents.items():
            agent = next((a for a in agents if (a.bmh or "").lower() == server_name.lower()), None)
            if agent is None:
                continue
            agents.remove(agent)
            for (am_mce, namespace), agent_machines in self._agent_machines.items():
                if am_mce != mce:
                    continue
                taken = [am for am in agent_machines if am.agent_name == agent.name]
                for agent_machine in taken:
                    agent_machines.remove(agent_machine)
                    self._replace_machine(mce, namespace, agent_machine.name)
            return True
        return False

    def _replace_machine(self, mce: str, namespace: str, agent_machine: str) -> None:
        machines = self._machines.get((mce, namespace), [])
        old = next((m for m in machines if m.infrastructure_ref == agent_machine), None)
        if old is None:
            return
        machines.remove(old)
        prefix = old.machine_set or old.name.rsplit("-", 1)[0]
        name = f"{prefix}-b{next(self._backfills):04d}"
        machines.append(
            MachineObservation(
                name=name,
                node_pool=old.node_pool,
                machine_set=old.machine_set,
                infrastructure_ref=name,
                phase="Pending",
                conditions=(
                    Condition(
                        "InfrastructureReady", "False", "NoSuitableAgents", "0 of 5 completed"
                    ),
                    Condition("NodeHealthy", "False", "WaitingForNodeRef", ""),
                ),
            )
        )
        self._agent_machines.setdefault((mce, namespace), []).append(
            AgentMachineObservation(name=name, conditions=(NO_SUITABLE_AGENTS,))
        )


def _lists[T](table: Mapping[Key, Iterable[T]] | None) -> dict[Key, list[T]]:
    return {key: list(values) for key, values in (table or {}).items()}
