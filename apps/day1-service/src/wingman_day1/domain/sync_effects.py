"""What a sync does to the nodes: the configs it removes and the nodepools that roll (ADR-0037).

A sync sets a nodepool's machine configs (ADR-0029) and its tuning profiles
(ADR-0061). OpenShift applies a MachineConfig change to every node of the
nodepool (drained and rebooted in place, or replaced, by the nodepool's
``upgradeType``), and a tuning change can reboot them too (a
PerformanceProfile, kernel arguments). Removed configs must be confirmed
by the person who asks for the sync; removed tuning profiles need no
confirmation, but every nodepool whose tuning changes is named.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from wingman_day1.domain.value_drift import NodepoolRef, ValueDrift, file_nodepools


@dataclass(frozen=True, slots=True)
class Removal:
    """A config a sync removes from a nodepool."""

    nodepool: NodepoolRef
    name: str


@dataclass(frozen=True, slots=True)
class Rebooting:
    """A nodepool whose configs or tuning a sync changes: merging rolls or reboots its nodes.

    How is the nodepool's own ``upgradeType`` (the chart's default is
    ``InPlace``: each node is drained and rebooted, ``inPlace.maxUnavailable``
    at a time, one when unset); ``Replace`` provisions new nodes instead.
    """

    nodepool: NodepoolRef
    replicas: int | None
    upgrade_type: str | None = None
    """The file's ``upgradeType``; ``None`` when unset (the chart's ``InPlace``)."""
    max_unavailable: int | str | None = None
    """The file's ``inPlace.maxUnavailable``; ``None`` when unset (one node at a time)."""
    configs: bool = True
    """Its machine configs change."""
    tuning: bool = False
    """Its tuning profiles change (ADR-0061): its nodes may reboot."""

    @property
    def replaces_nodes(self) -> bool:
        """``upgradeType: Replace``: new nodes are provisioned and the old ones removed."""
        return self.upgrade_type == "Replace"


def removals(decided: Sequence[ValueDrift]) -> tuple[Removal, ...]:
    """The configs the decided drift removes, nodepool by nodepool."""
    return tuple(
        Removal(d.nodepool, removed)
        for d in decided
        if d.is_configs and d.nodepool is not None
        for removed in d.removed
    )


def rebooting(values: Mapping[str, object], decided: Sequence[ValueDrift]) -> tuple[Rebooting, ...]:
    """Each nodepool whose configs or tuning the decided drift changes, once, in file order."""
    changing: dict[int, tuple[NodepoolRef, bool, bool]] = {}
    for d in decided:
        if not d.reboots or d.nodepool is None or not (d.added or d.removed):
            continue
        _, configs, tuning = changing.get(d.nodepool.index, (d.nodepool, False, False))
        changing[d.nodepool.index] = (d.nodepool, configs or d.is_configs, tuning or d.is_tuning)
    return tuple(
        _rebooting(values, ref, configs=configs, tuning=tuning)
        for _, (ref, configs, tuning) in sorted(changing.items())
    )


def _rebooting(
    values: Mapping[str, object], nodepool: NodepoolRef, *, configs: bool, tuning: bool
) -> Rebooting:
    pool = file_nodepools(values)[nodepool.index]
    found = cast("Mapping[str, object]", pool) if isinstance(pool, Mapping) else {}
    replicas = found.get("replicas")
    upgrade = found.get("upgradeType")
    in_place = found.get("inPlace")
    limit = (
        cast("Mapping[str, object]", in_place).get("maxUnavailable")
        if isinstance(in_place, Mapping)
        else None
    )
    return Rebooting(
        nodepool,
        replicas if isinstance(replicas, int) and not isinstance(replicas, bool) else None,
        upgrade if isinstance(upgrade, str) else None,
        limit if isinstance(limit, int | str) and not isinstance(limit, bool) else None,
        configs=configs,
        tuning=tuning,
    )


def confirmation_problems(
    planned: Sequence[Removal], confirmed: Sequence[tuple[int, str]]
) -> list[str]:
    """Planned removals the request does not confirm, and confirmed ones not planned."""
    want = Counter((r.nodepool.index, r.name) for r in planned)
    got = Counter(confirmed)
    problems = [
        f"nodepool[{index}].configs: the sync removes {name}; confirm it in confirm_removals"
        for (index, name), count in sorted(want.items())
        if got[(index, name)] < count
    ]
    problems += [
        f"nodepool[{index}].configs: confirm_removals names {name}, which the sync does not remove"
        for (index, name), count in sorted(got.items())
        if want[(index, name)] < count
    ]
    return problems


def nodes(replicas: int | None) -> str:
    """`` (3 nodes)``, or nothing when the count is unknown."""
    if replicas is None:
        return ""
    return f" ({replicas} node{'s' if replicas != 1 else ''})"


def how(rolling: Rebooting) -> str:
    """How the nodepool's nodes take the change, from its ``upgradeType``."""
    if rolling.replaces_nodes:
        return "replaced (`upgradeType: Replace`): new nodes are provisioned, then the old removed"
    at_a_time = (
        "one node at a time"
        if rolling.max_unavailable is None
        else f"`inPlace.maxUnavailable: {rolling.max_unavailable}` at a time"
    )
    return f"drained and rebooted in place, {at_a_time}"
