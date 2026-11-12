"""What an MCE has room for: free pods, servers of each node type, spare servers (ADR-0050).

**Free pods** are counted on the MCE's workers only (the user, 2026-11-12: a
production MCE has three masters, three infra nodes that run HAProxy and are
tainted so nothing is scheduled there, and its workers). A node is left out,
by the first reason that applies, when it has a control-plane (master) role,
has the infra role, is not Ready, is cordoned, or has a ``NoSchedule`` or
``NoExecute`` taint. Free pods are the remaining nodes'
``status.allocatable.pods``, less the pods bound to them that are not
``Succeeded`` or ``Failed``: what the scheduler counts against a node's limit.

**Servers of each node type**: for every InfraEnv the new cluster's
nodepools use, the MCE's free Agents there (the Agent provider's rule, as in
the nodes view: ``node_pools.why_not_free``), each joined to its server in
server-scan (``node_pools.ServerFinder``) and counted when that server is
usable. The new cluster needs at least its replicas of each type.

**Spare servers** come from server-scan's fleet rows: a row in
``INSTALLED_TO_INVENTORY`` registered to the MCE is in no cluster, and the
MCE keeps it to repair a cluster. A *usable* one is also out of maintenance,
reachable, not stale, neither ``CRITICAL`` nor ``UNKNOWN``, and not
contested. An MCE server-scan never names is unknown, never zero.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from wingman_day1.domain.machines import AgentObservation
from wingman_day1.domain.node_pools import ServerFinder, why_not_free
from wingman_day1.domain.servers import ServerRow

CONTROL_PLANE_ROLES: Final = (
    "node-role.kubernetes.io/master",
    "node-role.kubernetes.io/control-plane",
)
"""The node labels that make a node a control-plane node, whatever their value."""
INFRA_ROLE: Final = "node-role.kubernetes.io/infra"
"""The node label of an infra node (the MCE's HAProxy), whatever its value."""
BLOCKING_TAINTS: Final = frozenset({"NoSchedule", "NoExecute"})
"""Taint effects that keep pods off a node (``PreferNoSchedule`` only discourages)."""
TERMINAL_PHASES: Final = ("Succeeded", "Failed")
"""Pod phases that no longer take a slot on their node."""
SPARE_STATE: Final = "INSTALLED_TO_INVENTORY"
"""server-scan's ``openshift_state`` of a server registered to an MCE and in no cluster."""
UNUSABLE_HEALTH: Final = frozenset({"CRITICAL", "UNKNOWN"})


@dataclass(frozen=True, slots=True)
class NodeObservation:
    """One node of an MCE (``/api/v1/nodes``), as far as free pods need it."""

    name: str
    ready: bool
    """Its ``Ready`` condition is ``True``."""
    unschedulable: bool
    """``spec.unschedulable``: cordoned."""
    control_plane: bool
    """It carries a master or control-plane role label."""
    allocatable_pods: int
    """``status.allocatable.pods``; 0 when the node reports none."""
    infra: bool = False
    """It carries the infra role label."""
    tainted: bool = False
    """It has a ``NoSchedule`` or ``NoExecute`` taint."""


@dataclass(frozen=True, slots=True)
class ExcludedNodes:
    """How many nodes were left out of the free pods, by the first reason that applies."""

    control_plane: int = 0
    not_ready: int = 0
    unschedulable: int = 0
    infra: int = 0
    tainted: int = 0


@dataclass(frozen=True, slots=True)
class FreePods:
    """An MCE's free pods and how they were counted."""

    allocatable: int
    """The counted nodes' allocatable pods, summed."""
    used: int
    """Pods that are not ``Succeeded`` or ``Failed``, on the counted nodes."""
    nodes_counted: int
    excluded: ExcludedNodes

    @property
    def free(self) -> int:
        """Allocatable less used, never below zero."""
        return max(0, self.allocatable - self.used)


def counted(node: NodeObservation) -> bool:
    """Whether a node's pods count: a Ready, schedulable, untainted worker."""
    return exclusion(node) is None


def exclusion(node: NodeObservation) -> str | None:
    """Why a node's pods do not count, by the first reason that applies; ``None`` when they do."""
    for reason, applies in (
        ("control_plane", node.control_plane),
        ("infra", node.infra),
        ("not_ready", not node.ready),
        ("unschedulable", node.unschedulable),
        ("tainted", node.tainted),
    ):
        if applies:
            return reason
    return None


def free_pods(nodes: Iterable[NodeObservation], pods_per_node: Mapping[str, int]) -> FreePods:
    """The free pods on the counted nodes, given the non-terminal pods bound to each node."""
    allocatable = used = kept = 0
    excluded: dict[str, int] = {}
    for node in nodes:
        reason = exclusion(node)
        if reason is not None:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        kept += 1
        allocatable += node.allocatable_pods
        used += pods_per_node.get(node.name, 0)
    return FreePods(
        allocatable=allocatable,
        used=used,
        nodes_counted=kept,
        excluded=ExcludedNodes(**excluded),
    )


@dataclass(frozen=True, slots=True)
class SpareServers:
    """An MCE's spare servers in server-scan: every one, and those that could be used now."""

    total: int
    usable: int


def usable(row: ServerRow) -> bool:
    """A spare that could repair a cluster now: nothing about it says it cannot."""
    return (
        not row.maintenance
        and row.reachable
        and not row.stale
        and row.health not in UNUSABLE_HEALTH
        and not row.contested
    )


def spare_servers(rows: Iterable[ServerRow], scan_name: str) -> SpareServers | None:
    """The spare servers of the MCE server-scan calls ``scan_name``; ``None`` when it names none.

    server-scan's ``mce_name`` is matched exactly. An MCE that no row names,
    in any state, is unknown to server-scan: its spare count is unknown, not 0.
    """
    named = [row for row in rows if row.mce == scan_name]
    if not named:
        return None
    spare = [row for row in named if row.state == SPARE_STATE]
    return SpareServers(total=len(spare), usable=sum(1 for row in spare if usable(row)))


# ── Servers of each node type ────────────────────────────────────────────────


class Supply(StrEnum):
    """Whether an MCE has the servers of one node type that a new cluster needs."""

    ENOUGH = "pass"
    SHORT = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class NodeTypeSupply:
    """One node type (InfraEnv) on one MCE: what the new cluster needs, and what is free."""

    infra_env: str
    needed: int
    free_agents: int | None
    """Free Agents in the InfraEnv; ``None`` when the MCE's Agents could not be read."""
    healthy: int | None
    """Of those, the ones whose server-scan server is usable; ``None`` without server-scan."""
    not_in_server_scan: int = 0
    """Free Agents server-scan has no server for: neither healthy nor not."""
    health_checked: bool = True
    """``False`` when this deployment has no server-scan: free Agents are counted as they are."""

    @property
    def status(self) -> Supply:
        """Enough, short, or unknown (an unknown is never picked)."""
        if self.free_agents is None:
            return Supply.UNKNOWN
        if self.free_agents < self.needed:
            return Supply.SHORT
        if not self.health_checked:
            return Supply.ENOUGH
        if self.healthy is None:
            return Supply.UNKNOWN
        if self.healthy >= self.needed:
            return Supply.ENOUGH
        if self.healthy + self.not_in_server_scan >= self.needed:
            return Supply.UNKNOWN
        return Supply.SHORT

    @property
    def detail(self) -> str:
        """``dell-r660: 2 healthy free of 6 needed``, and what is not known."""
        if self.free_agents is None:
            return f"{self.infra_env}: {self.needed} needed; the MCE's Agents could not be read"
        if not self.health_checked:
            return (
                f"{self.infra_env}: {self.free_agents} free of {self.needed} needed, their health "
                "not checked (server-scan is not configured)"
            )
        if self.healthy is None:
            return (
                f"{self.infra_env}: {self.free_agents} free of {self.needed} needed, their "
                "health unknown without server-scan"
            )
        text = f"{self.infra_env}: {self.healthy} healthy free of {self.needed} needed"
        if self.not_in_server_scan:
            text += f" ({self.not_in_server_scan} more free, not in server-scan)"
        return text


def summed_needs(nodepools: Iterable[tuple[str, int]]) -> tuple[tuple[str, int], ...]:
    """Replicas per node type, summed over the nodepools that use it, sorted by type."""
    needs: dict[str, int] = {}
    for infra_env, replicas in nodepools:
        if replicas > 0:
            needs[infra_env] = needs.get(infra_env, 0) + replicas
    return tuple(sorted(needs.items()))


def node_type_supply(
    needs: Sequence[tuple[str, int]],
    agents: Sequence[AgentObservation] | None,
    rows: Sequence[ServerRow] | None,
    *,
    server_scan: bool = True,
) -> tuple[NodeTypeSupply, ...]:
    """For each need, the MCE's free Agents of that type and how many are healthy in server-scan.

    ``agents`` is ``None`` when the MCE's Agents could not be read, ``rows``
    when server-scan could not be. ``server_scan`` is ``False`` when this
    deployment has none: the free Agents are then counted without their health.
    """
    finder = ServerFinder(rows) if rows is not None else None
    supply: list[NodeTypeSupply] = []
    for infra_env, needed in needs:
        if agents is None:
            supply.append(NodeTypeSupply(infra_env, needed, None, None))
            continue
        free = [a for a in agents if a.infra_env == infra_env and why_not_free(a) is None]
        if not server_scan:
            supply.append(NodeTypeSupply(infra_env, needed, len(free), None, health_checked=False))
            continue
        if finder is None:
            supply.append(NodeTypeSupply(infra_env, needed, len(free), None))
            continue
        servers = [finder.find(agent) for agent in free]
        supply.append(
            NodeTypeSupply(
                infra_env,
                needed,
                len(free),
                healthy=sum(1 for row in servers if row is not None and usable(row)),
                not_in_server_scan=sum(1 for row in servers if row is None),
            )
        )
    return tuple(supply)
