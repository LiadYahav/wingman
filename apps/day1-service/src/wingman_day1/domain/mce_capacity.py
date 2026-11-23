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
usable. The new cluster needs at least its replicas of each type. A free
Agent that carries a used-Agent label (``used_agents``: herzi's
``redbull.io/ever-installed``, or the deployment's excluded labels) is no
free server: the new cluster's NodePools exclude it and herzi removes it; it
is counted apart (``used``).

A nodepool that draws from several InfraEnvs (ADR-0064) is one node type,
``a + b``: a free Agent of either counts for it. Node types that share an
InfraEnv are judged together, so no free server counts twice: their row is
all their InfraEnvs against all their replicas, and every part of it must
hold too (Hall's condition), so a nodepool that draws only from ``a`` is short
when ``a`` is, however many free ``b`` has.

**Spare servers** come from server-scan's fleet rows: a row in
``INSTALLED_TO_INVENTORY`` registered to the MCE is in no cluster, and the
MCE keeps it to repair a cluster. A *usable* one is also out of maintenance,
reachable, not stale, neither ``CRITICAL`` nor ``UNKNOWN``, and not
contested. An MCE server-scan never names is unknown, never zero.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import combinations
from typing import Final

from wingman_day1.domain.machines import AgentObservation
from wingman_day1.domain.node_pools import ServerFinder, why_not_free
from wingman_day1.domain.servers import ServerRow
from wingman_day1.domain.used_agents import used_label

CONTROL_PLANE_ROLES: Final = (
    "node-role.kubernetes.io/master",
    "node-role.kubernetes.io/control-plane",
)
"""The node labels that make a node a control-plane node, whatever their value."""
INFRA_ROLE: Final = "node-role.kubernetes.io/infra"
"""The node label of an infra node (the MCE's HAProxy), whatever its value."""
BLOCKING_TAINTS: Final = frozenset({"NoSchedule", "NoExecute"})
"""Taint effects that keep pods off a node (``PreferNoSchedule`` only discourages)."""
SPARE_STATE: Final = "INSTALLED_TO_INVENTORY"
"""server-scan's ``openshift_state`` of a server registered to an MCE and in no cluster."""
UNUSABLE_HEALTH: Final = frozenset({"CRITICAL", "UNKNOWN"})
TYPE_SEPARATOR: Final = " + "
"""Joins the InfraEnvs of a node type that has several, sorted (ADR-0064)."""
MAX_EXACT: Final = 10
"""Node types judged together up to this many are checked part by part; more, each alone."""


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


_SEVERITY: Final = {Supply.SHORT: 0, Supply.UNKNOWN: 1, Supply.ENOUGH: 2}


def node_type(infra_envs: Iterable[str]) -> str:
    """The node type of a nodepool that draws from ``infra_envs``: ``a``, or ``a + b``, sorted."""
    return TYPE_SEPARATOR.join(sorted(set(infra_envs)))


def infra_envs_in(node: str) -> tuple[str, ...]:
    """The InfraEnvs of a node type."""
    return tuple(node.split(TYPE_SEPARATOR))


@dataclass(frozen=True, slots=True)
class NodeTypeSupply:
    """One node type (InfraEnv, or several) on one MCE: what the new cluster needs, and is free."""

    infra_env: str
    """The node type: one InfraEnv, or several joined by `` + `` (ADR-0064)."""
    needed: int
    free_agents: int | None
    """Free Agents in its InfraEnvs; ``None`` when the MCE's Agents could not be read."""
    healthy: int | None
    """Of those, the ones whose server-scan server is usable; ``None`` without server-scan."""
    not_in_server_scan: int = 0
    """Free Agents server-scan has no server for: neither healthy nor not."""
    health_checked: bool = True
    """``False`` when this deployment has no server-scan: free Agents are counted as they are."""
    within: NodeTypeSupply | None = None
    """A part of it that falls shorter, for the nodepools that draw only on that part."""
    used: int = 0
    """Free Agents left out: they carry a used-Agent label, and herzi removes them."""

    @property
    def infra_envs(self) -> tuple[str, ...]:
        """The InfraEnvs whose free Agents it counts."""
        return infra_envs_in(self.infra_env)

    @property
    def status(self) -> Supply:
        """Enough, short, or unknown (never picked); a part that falls shorter decides."""
        own = self._own_status
        if self.within is None or _SEVERITY[own] <= _SEVERITY[self.within.status]:
            return own
        return self.within.status

    @property
    def _own_status(self) -> Supply:
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
        """``dell-r660: 2 healthy free of 6 needed``, what is not known, and a short part."""
        if self.within is not None:
            return f"{replace(self, within=None).detail}; of those, {self.within.detail}"
        if self.free_agents is None:
            return f"{self.infra_env}: {self.needed} needed; the MCE's Agents could not be read"
        if not self.health_checked:
            text = (
                f"{self.infra_env}: {self.free_agents} free of {self.needed} needed, their health "
                "not checked (server-scan is not configured)"
            )
        elif self.healthy is None:
            text = (
                f"{self.infra_env}: {self.free_agents} free of {self.needed} needed, their "
                "health unknown without server-scan"
            )
        else:
            text = f"{self.infra_env}: {self.healthy} healthy free of {self.needed} needed"
            if self.not_in_server_scan:
                text += f" ({self.not_in_server_scan} more free, not in server-scan)"
        if self.used:
            text += f"; {self.used} used, left out (herzi removes {_them(self.used)})"
        return text


def summed_needs(nodepools: Iterable[tuple[str, int]]) -> tuple[tuple[str, int], ...]:
    """Replicas per node type, summed over the nodepools that use it, sorted by type."""
    needs: dict[str, int] = {}
    for node, replicas in nodepools:
        if replicas > 0:
            key = node_type(infra_envs_in(node))
            needs[key] = needs.get(key, 0) + replicas
    return tuple(sorted(needs.items()))


def judged_together(needs: Sequence[tuple[str, int]]) -> list[list[tuple[str, int]]]:
    """The needs in groups whose node types share InfraEnvs, each group in the needs' order."""
    groups: list[list[tuple[str, int]]] = []
    for need in needs:
        mine = set(infra_envs_in(need[0]))
        joined = [g for g in groups if any(mine.intersection(infra_envs_in(t)) for t, _ in g)]
        rest = [g for g in groups if all(g is not j for j in joined)]
        groups = [*rest, [*(n for g in joined for n in g), need]]
    return sorted(groups, key=lambda group: needs.index(group[0]))


def node_type_supply(
    needs: Sequence[tuple[str, int]],
    agents: Sequence[AgentObservation] | None,
    rows: Sequence[ServerRow] | None,
    *,
    server_scan: bool = True,
    used_labels: Sequence[str] = (),
) -> tuple[NodeTypeSupply, ...]:
    """For each need, the MCE's free Agents of that type and how many are healthy in server-scan.

    ``agents`` is ``None`` when the MCE's Agents could not be read, ``rows``
    when server-scan could not be. ``server_scan`` is ``False`` when this
    deployment has none: the free Agents are then counted without their health.
    A free Agent carrying one of ``used_labels`` is no free server, counted as
    ``used``. Needs whose node types share an InfraEnv are one row
    (:func:`judged_together`).
    """
    finder = ServerFinder(rows) if rows is not None else None
    count = _Count(agents, finder, server_scan, used_labels)
    return tuple(_judged(group, count) for group in judged_together(needs))


def _judged(group: Sequence[tuple[str, int]], count: _Count) -> NodeTypeSupply:
    """A group's row: all of it, with the part that falls shortest when that one is worse."""
    whole = count.supply(group)
    if len(group) == 1:
        return whole
    worst = min((count.supply(part) for part in _parts(group)), key=lambda s: _SEVERITY[s.status])
    if _SEVERITY[worst.status] < _SEVERITY[whole.status]:
        return replace(whole, within=worst)
    return whole


def _parts(group: Sequence[tuple[str, int]]) -> list[Sequence[tuple[str, int]]]:
    """Every part of a group but the whole, up to :data:`MAX_EXACT` needs; else each need alone."""
    if len(group) > MAX_EXACT:
        return [[need] for need in group]
    return [part for size in range(1, len(group)) for part in combinations(group, size)]


class _Count:
    """The MCE's free Agents per InfraEnv and their health, counted once: a node type sums its own.

    Every Agent is in one InfraEnv, so a sum over a set of InfraEnvs counts
    each free server once.
    """

    def __init__(
        self,
        agents: Sequence[AgentObservation] | None,
        finder: ServerFinder | None,
        server_scan: bool,
        used_labels: Sequence[str],
    ) -> None:
        self._known = agents is not None
        self._checked = server_scan
        finder = finder if server_scan else None
        self._health_known = finder is not None
        self._free: dict[str, int] = {}
        self._healthy: dict[str, int] = {}
        self._missing: dict[str, int] = {}
        self._used: dict[str, int] = {}
        for agent in agents or ():
            if agent.infra_env is None or why_not_free(agent) is not None:
                continue
            if used_label(agent, used_labels) is not None:
                _add(self._used, agent.infra_env)
                continue
            _add(self._free, agent.infra_env)
            row = finder.find(agent) if finder is not None else None
            if finder is not None and row is None:
                _add(self._missing, agent.infra_env)
            elif row is not None and usable(row):
                _add(self._healthy, agent.infra_env)

    def supply(self, needs: Sequence[tuple[str, int]]) -> NodeTypeSupply:
        """What the needs' InfraEnvs, together, have free for all of the needs."""
        envs = {env for node, _ in needs for env in infra_envs_in(node)}
        label, needed = node_type(envs), sum(replicas for _, replicas in needs)
        if not self._known:
            return NodeTypeSupply(label, needed, None, None)
        free = sum(self._free.get(env, 0) for env in envs)
        used = sum(self._used.get(env, 0) for env in envs)
        if not self._checked:
            return NodeTypeSupply(label, needed, free, None, health_checked=False, used=used)
        if not self._health_known:
            return NodeTypeSupply(label, needed, free, None, used=used)
        healthy = sum(self._healthy.get(env, 0) for env in envs)
        missing = sum(self._missing.get(env, 0) for env in envs)
        return NodeTypeSupply(
            label, needed, free, healthy=healthy, not_in_server_scan=missing, used=used
        )


def _add(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _them(count: int) -> str:
    return "it" if count == 1 else "them"
