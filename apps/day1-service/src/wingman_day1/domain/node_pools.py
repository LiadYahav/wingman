"""A hosted cluster's nodes by NodePool: what is there, what is missing and why (ADR-0038).

The MCE hub's objects are joined here, pure:

    NodePool  <- Machine (annotation hypershift.openshift.io/nodePool = <ns>/<pool>)
    Machine   -> AgentMachine (spec.infrastructureRef) -> Agent (status.agentRef)
    Agent     -> BareMetalHost (label agent-install.openshift.io/bmh) = server-scan's server

and each Machine gets a state, what is happening to it now, whether the
pool's update is working on it, and, when it waits, why. The rules are
``docs/notes/2026-11-11-cluster-nodes-api.md`` §1; what each object says and
where upstream sets it is ``docs/ecosystem/notes/hypershift-node-state.md``.

Only the MCE is read, never a hosted cluster's own API. So an InPlace
update's drain before a reboot, and which node it takes next, are not
visible: the hub shows a node only once its reboot makes it not ready.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from wingman_day1.domain.machines import (
    AgentMachineObservation,
    AgentObservation,
    MachineObservation,
    MachineSetObservation,
    condition,
    is_true,
)
from wingman_day1.domain.names import HostedClusterRef
from wingman_day1.domain.selectors import selects
from wingman_day1.domain.servers import ServerRow, node_cluster_names
from wingman_day1.domain.status import (
    INPLACE_FAILED,
    UPDATE_CONDITIONS,
    Autoscaling,
    Condition,
    HostedClusterObservation,
    NodePoolObservation,
)

IN_PLACE: Final = "InPlace"
REPLACE: Final = "Replace"
PROBLEM_CONDITIONS: Final = ("Ready", "AllMachinesReady", "AllNodesHealthy")
INSTALLED_AGENT_STATES: Final = frozenset({"installed", "added-to-existing-cluster"})
_PROGRESS: Final = re.compile(r"Total Nodes: (\d+)\. Upgraded: (\d+)")
_DEGRADED: Final = re.compile(r"Node (\S+) in nodepool degraded: (.*)", re.DOTALL)

DELETION_STEPS_V1BETA2: Final = {
    "WaitingForPreDrainHook": "Waiting for a pre-drain hook",
    "DrainingNode": "Draining",
    "WaitingForVolumeDetach": "Waiting for volumes to detach",
    "WaitingForPreTerminateHook": "Waiting for the host to return to discovery",
    "WaitingForInfrastructureDeletion": "Waiting for its AgentMachine to be deleted",
    "WaitingForBootstrapDeletion": "Waiting for its bootstrap data to be deleted",
    "DeletingNode": "Deleting its Node",
    "DeletionCompleted": "Deleted",
}
"""CAPI's v1beta2 ``Deleting`` reasons (4.19+ hosted clusters), in words."""
DELETION_STEPS_V1BETA1: Final = (
    ("PreDrainDeleteHookSucceeded", "Waiting for a pre-drain hook"),
    ("DrainingSucceeded", "Draining"),
    ("VolumeDetachSucceeded", "Waiting for volumes to detach"),
    ("PreTerminateDeleteHookSucceeded", "Waiting for the host to return to discovery"),
)
"""CAPI's v1beta1 deletion conditions, in the order a deletion meets them.

The last is the Agent provider's hook: it holds the Machine until its host
reboots into discovery.
"""


class NodeState(StrEnum):
    """A node's state; the order here is the order nodes are listed in."""

    FAILED = "failed"
    DELETING = "deleting"
    WAITING = "waiting"
    MISSING = "missing"
    INSTALLING = "installing"
    JOINING = "joining"
    NOT_READY = "not_ready"
    READY = "ready"


_STATE_ORDER: Final = {state: index for index, state in enumerate(NodeState)}
_REPLACE_CURRENT: Final = frozenset(
    {NodeState.DELETING, NodeState.INSTALLING, NodeState.JOINING, NodeState.WAITING}
)


@dataclass(frozen=True, slots=True)
class ClusterMachines:
    """Everything the hub holds about one cluster's workers."""

    hosted_cluster: HostedClusterObservation
    node_pools: Sequence[NodePoolObservation]
    machines: Sequence[MachineObservation] = ()
    machine_sets: Sequence[MachineSetObservation] = ()
    agent_machines: Sequence[AgentMachineObservation] = ()
    agents: Sequence[AgentObservation] | None = None
    """``None`` when they could not be read (no agent namespace): free Agents are unknown."""


@dataclass(frozen=True, slots=True)
class UpdateProgress:
    """An in-place update's ``Total Nodes: n. Upgraded: k``."""

    total: int
    updated: int


@dataclass(frozen=True, slots=True)
class PoolUpdate:
    """A NodePool update in progress (or failed in place)."""

    kind: str
    """``version``, ``config`` or ``machine_template``."""
    message: str
    progress: UpdateProgress | None = None
    failed: bool = False


@dataclass(frozen=True, slots=True)
class FreeAgents:
    """The Agents a NodePool's selector matches, and how many of them are free."""

    matching: int
    free: int
    not_free: tuple[tuple[str, int], ...] = ()
    """Why the others are not free, most common first: ``("bound", 3)``, ..."""


@dataclass(frozen=True, slots=True)
class AgentSummary:
    """The Agent reserved for a Machine."""

    name: str
    state: str | None
    stage: str | None


@dataclass(frozen=True, slots=True)
class NodeView:
    """One node of a pool: a Machine, or one the pool wants and has not got."""

    state: NodeState
    machine: str | None = None
    node_name: str | None = None
    current: bool = False
    activity: str | None = None
    waiting_for: str | None = None
    outdated: bool | None = None
    agent: AgentSummary | None = None
    server_name: str | None = None
    """server-scan's name when it knows the server, else the BareMetalHost's."""
    server: ServerRow | None = None


@dataclass(frozen=True, slots=True)
class NodePoolView:
    """A NodePool, its update and problems, and its nodes."""

    name: str
    wanted: int | None
    """``spec.replicas`` (0 when unset); ``None`` only when the pool autoscales."""
    autoscaling: Autoscaling | None
    ready: int
    """``status.replicas``, 0 when unset."""
    version: str | None
    upgrade_type: str | None
    agent_selector: str | None
    update: PoolUpdate | None
    problems: tuple[str, ...]
    free_agents: FreeAgents | None
    nodes: tuple[NodeView, ...]


@dataclass(frozen=True, slots=True)
class NodesByPool:
    """A cluster's NodePools with their nodes, and the servers no Machine leads to."""

    node_pools: tuple[NodePoolView, ...]
    unassigned: tuple[ServerRow, ...]

    def servers(self) -> list[ServerRow]:
        """Every server shown: the nodes' and the unassigned ones."""
        nodes = [n.server for p in self.node_pools for n in p.nodes if n.server is not None]
        return [*nodes, *self.unassigned]

    def leads_to(self, server_id: str, server_name: str) -> bool:
        """Whether a Machine of the cluster leads to this server (by id, or by name)."""
        name = server_name.lower()
        return any(
            (node.server is not None and node.server.id == server_id)
            or (node.server_name is not None and node.server_name.lower() == name)
            for pool in self.node_pools
            for node in pool.nodes
        )


# ── The join ─────────────────────────────────────────────────────────────────


def nodes_by_pool(
    hosted: HostedClusterRef,
    observed: ClusterMachines,
    servers: Sequence[ServerRow] | None,
) -> NodesByPool:
    """Each NodePool with its nodes, and the servers no Machine leads to.

    ``unassigned`` holds the servers server-scan places in the cluster that no
    Machine leads to; it is empty when server-scan is not read.
    """
    finder = ServerFinder(servers or ())
    agent_machines = {am.name: am for am in observed.agent_machines}
    agents = {agent.name: agent for agent in observed.agents or ()}
    pools = tuple(
        _pool_view(
            pool,
            [m for m in observed.machines if m.node_pool == f"{hosted.namespace}/{pool.name}"],
            [s for s in observed.machine_sets if _set_of(s, pool.name, hosted.namespace)],
            agent_machines=agent_machines,
            agents=agents,
            all_agents=observed.agents,
            finder=finder,
        )
        for pool in sorted(observed.node_pools, key=lambda pool: pool.name)
    )
    reached = {node.server.id for pool in pools for node in pool.nodes if node.server}
    names = node_cluster_names(hosted)
    unassigned = tuple(
        sorted(
            (r for r in servers or () if r.cluster_name in names and r.id not in reached),
            key=lambda row: (row.name, row.id),
        )
    )
    return NodesByPool(node_pools=pools, unassigned=unassigned)


def _set_of(machine_set: MachineSetObservation, pool: str, namespace: str) -> bool:
    """Whether a MachineSet is the pool's: by annotation, else by name (InPlace) or label."""
    if machine_set.node_pool is not None:
        return machine_set.node_pool == f"{namespace}/{pool}"
    return pool in (machine_set.name, machine_set.deployment)


def _pool_view(
    pool: NodePoolObservation,
    machines: Sequence[MachineObservation],
    machine_sets: Sequence[MachineSetObservation],
    *,
    agent_machines: Mapping[str, AgentMachineObservation],
    agents: Mapping[str, AgentObservation],
    all_agents: Sequence[AgentObservation] | None,
    finder: ServerFinder,
) -> NodePoolView:
    update = pool_update(pool.conditions, machine_sets)
    degraded = degraded_node(pool.conditions, machine_sets)
    free = free_agents(pool, all_agents)
    newest = newest_machine_set(machine_sets) if pool.upgrade_type == REPLACE else None
    wanted = (pool.replicas or 0) if pool.autoscaling is None else None
    nodes = [
        _node_view(
            machine,
            pool,
            agent_machine=agent_machines.get(machine.infrastructure_ref or machine.name),
            agents=agents,
            update=update,
            degraded=degraded,
            free=free,
            newest=newest,
            finder=finder,
        )
        for machine in machines
    ]
    nodes += missing_nodes(wanted, machines)
    return NodePoolView(
        name=pool.name,
        wanted=wanted,
        autoscaling=pool.autoscaling,
        ready=pool.current_replicas,
        version=pool.version,
        upgrade_type=pool.upgrade_type,
        agent_selector=pool.agent_selector.describe() if pool.agent_selector else None,
        update=update,
        problems=pool_problems(pool.conditions),
        free_agents=free,
        nodes=tuple(sorted(nodes, key=_node_order)),
    )


def _node_view(
    machine: MachineObservation,
    pool: NodePoolObservation,
    *,
    agent_machine: AgentMachineObservation | None,
    agents: Mapping[str, AgentObservation],
    update: PoolUpdate | None,
    degraded: tuple[str, str] | None,
    free: FreeAgents | None,
    newest: str | None,
    finder: ServerFinder,
) -> NodeView:
    agent_name = (agent_machine.agent_name if agent_machine else None) or machine.agent_name
    agent = agents.get(agent_name) if agent_name else None
    is_degraded = degraded is not None and machine.node_name == degraded[0]
    state = node_state(machine, agent_machine, agent, degraded=is_degraded)
    in_place = pool.upgrade_type == IN_PLACE
    server = finder.find(agent) if agent else None
    return NodeView(
        state=state,
        machine=machine.name,
        node_name=machine.node_name,
        current=is_current(state, pool.upgrade_type, update, degraded=is_degraded),
        activity=activity(
            state,
            machine,
            agent,
            updating_in_place=in_place and update is not None,
            degraded_reason=degraded[1] if degraded and is_degraded else None,
        ),
        waiting_for=(
            waiting_for(agent_machine, free, pool) if state is NodeState.WAITING else None
        ),
        outdated=(machine.machine_set != newest) if newest is not None else None,
        agent=AgentSummary(agent.name, agent.state, agent.stage) if agent else None,
        server_name=server.name if server else (agent.bmh if agent else None),
        server=server,
    )


# ── The rules, one function each ─────────────────────────────────────────────


def node_state(
    machine: MachineObservation,
    agent_machine: AgentMachineObservation | None,
    agent: AgentObservation | None,
    *,
    degraded: bool = False,
) -> NodeState:
    """The state, by the first rule that holds (contract §1)."""
    if machine.deleting:
        return NodeState.DELETING
    if machine.phase == "Failed" or degraded:
        return NodeState.FAILED
    if not _reserved(machine, agent_machine):
        return NodeState.WAITING
    if machine.node_name:
        return (
            NodeState.READY if is_true(machine.conditions, "NodeHealthy") else NodeState.NOT_READY
        )
    if not _installed(agent_machine, agent):
        return NodeState.INSTALLING
    return NodeState.JOINING


def _reserved(machine: MachineObservation, agent_machine: AgentMachineObservation | None) -> bool:
    """An Agent is reserved for it (``AgentReserved`` True), or it plainly has one."""
    if machine.node_name or machine.agent_name:
        return True
    if agent_machine is None:
        return False
    return (
        is_true(agent_machine.conditions, "AgentReserved") or agent_machine.agent_name is not None
    )


def _installed(
    agent_machine: AgentMachineObservation | None, agent: AgentObservation | None
) -> bool:
    if agent is not None and (
        agent.state in INSTALLED_AGENT_STATES or is_true(agent.conditions, "Installed")
    ):
        return True
    return agent_machine is not None and is_true(agent_machine.conditions, "Installed")


def is_current(
    state: NodeState, upgrade_type: str | None, update: PoolUpdate | None, *, degraded: bool
) -> bool:
    """Whether the pool's update is working on this node now (contract §1, ``current``)."""
    if upgrade_type == IN_PLACE:
        return degraded or (update is not None and state is NodeState.NOT_READY)
    if upgrade_type == REPLACE:
        return update is not None and state in _REPLACE_CURRENT
    return False


def activity(
    state: NodeState,
    machine: MachineObservation,
    agent: AgentObservation | None,
    *,
    updating_in_place: bool,
    degraded_reason: str | None,
) -> str | None:
    """What is happening to the node now, in words; ``None`` when nothing is."""
    match state:
        case NodeState.DELETING:
            return deletion_step(machine)
        case NodeState.FAILED:
            if degraded_reason is not None:
                return degraded_reason
            failure = machine.failure_message or machine.failure_reason
            return f"Failed: {failure}" if failure else None
        case NodeState.INSTALLING:
            if agent is not None and agent.stage:
                return f"Installing: {agent.stage}"
            if agent is not None and agent.state:
                return f"Installing ({agent.state})"
            return "Installing"
        case NodeState.JOINING:
            return "Joining the cluster"
        case NodeState.NOT_READY:
            why = _node_health(machine)
            return (
                f"Rebooting for the update ({why})"
                if updating_in_place
                else f"Node not ready: {why}"
            )
        case _:
            return None


def _node_health(machine: MachineObservation) -> str:
    health = condition(machine.conditions, "NodeHealthy")
    if health is None:
        return "NodeHealthy is not reported"
    return _sentence(health.message) or health.reason or f"NodeHealthy is {health.status}"


def deletion_step(machine: MachineObservation) -> str:
    """The deletion step a deleting Machine is on: v1beta2 ``Deleting``, else the first unmet."""
    deleting = condition(machine.v1beta2_conditions, "Deleting")
    if deleting is not None and deleting.status == "True" and deleting.reason:
        return DELETION_STEPS_V1BETA2.get(deleting.reason, deleting.reason)
    for kind, words in DELETION_STEPS_V1BETA1:
        found = condition(machine.conditions, kind)
        if found is not None and found.status == "False":
            if found.reason == "DrainingFailed":
                return f"Draining failed: {_sentence(found.message)}".rstrip(": ")
            return words
    return "Deleting"


def waiting_for(
    agent_machine: AgentMachineObservation | None,
    free: FreeAgents | None,
    pool: NodePoolObservation,
) -> str:
    """Why no Agent is reserved for a Machine, from its AgentMachine and the pool's Agents."""
    if agent_machine is None:
        return "Its AgentMachine does not exist yet"
    reserved = condition(agent_machine.conditions, "AgentReserved")
    if reserved is not None and reserved.reason == "AgentNotYetFound" and reserved.message:
        return f"No Agent reserved yet: {_sentence(reserved.message)}"
    if free is None:
        reason = f" ({reserved.reason})" if reserved is not None and reserved.reason else ""
        return f"No Agent is reserved for it{reason}; the Agents could not be counted"
    selector = pool.agent_selector.describe() if pool.agent_selector else None
    if free.matching == 0:
        return (
            f"No Agent matches this NodePool's selector ({selector})"
            if selector
            else "There is no Agent in the cluster's agent namespace"
        )
    if free.free == 0:
        why = ", ".join(f"{count} {reason}" for reason, count in free.not_free)
        return (
            f"No free Agent matches this NodePool: {_agents_match(free.matching)} its selector, "
            f"none is free ({why})"
        )
    if free.free == 1:
        return "Waiting for the Agent provider to reserve the 1 free Agent"
    return f"Waiting for the Agent provider to reserve one of the {free.free} free Agents"


def _agents_match(count: int) -> str:
    return f"{count} Agent matches" if count == 1 else f"{count} Agents match"


def missing_nodes(wanted: int | None, machines: Sequence[MachineObservation]) -> list[NodeView]:
    """One ``missing`` row per Machine the pool wants beyond its non-deleting ones."""
    have = sum(1 for machine in machines if not machine.deleting)
    if wanted is None or wanted <= have:
        return []
    missing = wanted - have
    rest = "one is still to be created" if missing == 1 else f"{missing} are still to be created"
    nodes = "node" if wanted == 1 else "nodes"
    machines_word = "Machine" if have == 1 else "Machines"
    why = f"The NodePool wants {wanted} {nodes} and has {have} {machines_word}; {rest}"
    return [NodeView(state=NodeState.MISSING, waiting_for=why) for _ in range(missing)]


def pool_update(
    conditions: tuple[Condition, ...], machine_sets: Iterable[MachineSetObservation] = ()
) -> PoolUpdate | None:
    """The update in progress: the first updating condition that is not False.

    An in-place update that failed is False with ``InplaceUpgradeFailed``; it
    is still shown, with ``failed`` set. Progress comes from the condition's
    text (4.19+ operators) or the MachineSet's annotation (4.16 to 4.18).
    """
    for kind_type, kind in UPDATE_CONDITIONS:
        found = condition(conditions, kind_type)
        if found is None or (found.status == "False" and found.reason != INPLACE_FAILED):
            continue
        progress = update_progress(found.message)
        if progress is None:
            progress = next(
                (p for s in machine_sets if (p := update_progress(s.upgrade_in_progress))), None
            )
        return PoolUpdate(
            kind=kind,
            message=found.message,
            progress=progress,
            failed=found.reason == INPLACE_FAILED,
        )
    return None


def update_progress(text: str | None) -> UpdateProgress | None:
    """``Total Nodes: n. Upgraded: k`` from an in-place update's text."""
    found = _PROGRESS.search(text or "")
    return UpdateProgress(total=int(found[1]), updated=int(found[2])) if found else None


def degraded_node(
    conditions: tuple[Condition, ...], machine_sets: Iterable[MachineSetObservation] = ()
) -> tuple[str, str] | None:
    """The Node an in-place update names as degraded, and why.

    The text is ``Node <n> in nodepool degraded: <reason>``, in a failed
    updating condition (4.19+) or the MachineSet's annotation.
    """
    texts = [
        c.message
        for kind, _ in UPDATE_CONDITIONS
        if (c := condition(conditions, kind)) is not None and c.reason == INPLACE_FAILED
    ]
    texts += [s.upgrade_degraded for s in machine_sets if s.upgrade_degraded]
    for text in texts:
        found = _DEGRADED.search(text)
        if found:
            return found[1], _sentence(found[2]) or "degraded"
    return None


def pool_problems(conditions: tuple[Condition, ...]) -> tuple[str, ...]:
    """The pool's ``Ready``, ``AllMachinesReady``, ``AllNodesHealthy`` that are not True.

    Each is ``Type: reason: message``, empty parts left out, the message on one line.
    """
    problems = []
    for kind in PROBLEM_CONDITIONS:
        found = condition(conditions, kind)
        if found is not None and found.status != "True":
            parts = (kind, found.reason, _one_line(found.message))
            problems.append(": ".join(part for part in parts if part))
    return tuple(problems)


def free_agents(
    pool: NodePoolObservation, agents: Sequence[AgentObservation] | None
) -> FreeAgents | None:
    """The Agents the pool's selector matches, and how many the provider could take."""
    if agents is None:
        return None
    reasons = Counter(
        why_not_free(agent) for agent in agents if selects(pool.agent_selector, agent.labels)
    )
    matching = sum(reasons.values())
    free = reasons.pop(None, 0)
    not_free = tuple(
        (reason, count)
        for reason, count in sorted(reasons.items(), key=lambda item: (-item[1], str(item[0])))
        if reason is not None
    )
    return FreeAgents(matching=matching, free=free, not_free=not_free)


def why_not_free(agent: AgentObservation) -> str | None:
    """Why the Agent provider would not take this Agent; ``None`` when it would.

    Its rule (``isValidAgent``): no ``agentMachineRef`` label, approved,
    ``Validated`` and ``Connected`` True, ``Bound`` False.
    """
    bound = condition(agent.conditions, "Bound")
    if agent.taken_by is not None or bound is None or bound.status != "False":
        return "bound"
    if not agent.approved:
        return "not approved"
    if not is_true(agent.conditions, "Connected"):
        return "not connected"
    if not is_true(agent.conditions, "Validated"):
        return "not validated"
    return None


def newest_machine_set(machine_sets: Sequence[MachineSetObservation]) -> str | None:
    """The MachineSet with the highest revision: the one a Replace rollout moves to."""
    revised = [s for s in machine_sets if s.revision is not None]
    if not revised:
        return None
    return max(revised, key=lambda s: (s.revision or 0, s.name)).name


def _node_order(node: NodeView) -> tuple[int, str]:
    return _STATE_ORDER[node.state], node.server_name or node.machine or ""


def _sentence(text: str) -> str:
    """One line, without its trailing period and space."""
    return _one_line(text).rstrip(". ").strip()


def _one_line(text: str) -> str:
    return "; ".join(line.strip() for line in text.splitlines() if line.strip())


# ── Agent -> server ──────────────────────────────────────────────────────────


class ServerFinder:
    """server-scan's server for an Agent: by its BareMetalHost name, then MAC, then serial.

    A BareMetalHost name is a Kubernetes name (lowercase), so names are
    compared ignoring case. server-scan names are not unique, so a name that
    several servers share is settled by MAC or serial, or not at all.
    """

    def __init__(self, rows: Iterable[ServerRow]) -> None:
        """Index ``rows``, normally the whole fleet."""
        self._by_name: dict[str, list[ServerRow]] = defaultdict(list)
        self._by_mac: dict[str, list[ServerRow]] = defaultdict(list)
        self._by_serial: dict[str, list[ServerRow]] = defaultdict(list)
        for row in rows:
            self._by_name[row.name.lower()].append(row)
            for mac in row.macs:
                self._by_mac[mac.lower()].append(row)
            if row.serial:
                self._by_serial[row.serial.lower()].append(row)

    def find(self, agent: AgentObservation) -> ServerRow | None:
        """The one server this Agent is, or ``None``."""
        by_mac = {row.id: row for mac in agent.macs for row in self._by_mac.get(mac.lower(), [])}
        by_serial = {row.id: row for row in self._by_serial.get((agent.serial or "").lower(), [])}
        if agent.bmh:
            named = {row.id: row for row in self._by_name.get(agent.bmh.lower(), [])}
            if len(named) == 1:
                return next(iter(named.values()))
            for narrowed in (named.keys() & by_mac.keys(), named.keys() & by_serial.keys()):
                if len(narrowed) == 1:
                    return named[next(iter(narrowed))]
            if named:
                return None
        for candidates in (by_mac, by_serial):
            if len(candidates) == 1:
                return next(iter(candidates.values()))
        return None
