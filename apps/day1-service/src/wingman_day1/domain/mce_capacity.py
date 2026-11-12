"""What an MCE has room for: its free pods, and its spare servers (ADR-0050).

**Free pods** (decision 16 of the plan, ``docs/ideas/single-pane.md``) are
counted on every Ready, schedulable node of the MCE, control-plane (master)
nodes excluded: the sum of those nodes' ``status.allocatable.pods``, less the
pods bound to them that are not ``Succeeded`` or ``Failed``. That is what the
scheduler counts against a node's pod limit, and a hosted control plane is
about 70 pods. A node with a control-plane role is excluded even when it is
also a worker (a compact hub then has no free pods).

**Spare servers** (decision 7) come from server-scan's fleet rows: a row in
``INSTALLED_TO_INVENTORY`` registered to the MCE is in no cluster, and the
MCE keeps it to repair a cluster. A *usable* spare is also out of
maintenance, reachable, not stale, neither ``CRITICAL`` nor ``UNKNOWN``, and
not contested. An MCE server-scan never names is unknown, never zero.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from wingman_day1.domain.servers import ServerRow

CONTROL_PLANE_ROLES: Final = (
    "node-role.kubernetes.io/master",
    "node-role.kubernetes.io/control-plane",
)
"""The node labels that make a node a control-plane node, whatever their value."""
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


@dataclass(frozen=True, slots=True)
class ExcludedNodes:
    """How many nodes were left out of the free pods, by the first reason that applies."""

    control_plane: int = 0
    not_ready: int = 0
    unschedulable: int = 0


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
    """Whether a node's pods count: Ready, schedulable and not a control-plane node."""
    return node.ready and not node.unschedulable and not node.control_plane


def free_pods(nodes: Iterable[NodeObservation], pods_per_node: Mapping[str, int]) -> FreePods:
    """The free pods on the counted nodes, given the non-terminal pods bound to each node."""
    allocatable = used = kept = 0
    control_plane = not_ready = unschedulable = 0
    for node in nodes:
        if node.control_plane:
            control_plane += 1
        elif not node.ready:
            not_ready += 1
        elif node.unschedulable:
            unschedulable += 1
        else:
            kept += 1
            allocatable += node.allocatable_pods
            used += pods_per_node.get(node.name, 0)
    return FreePods(
        allocatable=allocatable,
        used=used,
        nodes_counted=kept,
        excluded=ExcludedNodes(control_plane, not_ready, unschedulable),
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
