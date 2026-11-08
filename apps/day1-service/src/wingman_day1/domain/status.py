"""Live state of a hosted cluster, as its MCE hub reports it.

The hub API adapter returns these observations; the rules that turn
HyperShift conditions into problems are here, pure. They are the legacy
service's rules, unchanged: a HostedCluster is healthy when ``Available`` is
True and neither ``Degraded`` nor ``Progressing`` is; a NodePool when
``Ready`` is True and it is not updating.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Final

HOSTED_CLUSTER_MUST_BE_TRUE: Final = ("Available",)
HOSTED_CLUSTER_MUST_NOT_BE_TRUE: Final = ("Degraded", "Progressing")
NODE_POOL_MUST_BE_TRUE: Final = ("Ready",)
NODE_POOL_MUST_NOT_BE_TRUE: Final = ("UpdatingVersion", "UpdatingConfig")


@dataclass(frozen=True, slots=True)
class Condition:
    """One Kubernetes status condition."""

    type: str
    status: str
    reason: str = ""
    message: str = ""


@dataclass(frozen=True, slots=True)
class HostedClusterObservation:
    """A HostedCluster's status, as read from the hub."""

    name: str
    namespace: str
    phase: str | None
    version: str | None
    """The newest entry of ``status.version.history``."""
    conditions: tuple[Condition, ...] = ()


@dataclass(frozen=True, slots=True)
class NodePoolObservation:
    """A NodePool's status, as read from the hub.

    HyperShift NodePools have no ``readyReplicas``: ``current_replicas`` is
    ``status.replicas`` and ``desired_replicas`` is ``spec.replicas``.
    """

    name: str
    desired_replicas: int
    current_replicas: int
    conditions: tuple[Condition, ...] = ()


def condition_problems(
    conditions: Iterable[Condition],
    *,
    must_be_true: Iterable[str],
    must_not_be_true: Iterable[str],
) -> list[str]:
    """Human-readable problems; empty when every rule holds."""
    by_type = {c.type: c for c in conditions}
    problems: list[str] = []
    for kind in must_be_true:
        condition = by_type.get(kind)
        if condition is None:
            problems.append(f"{kind}: condition not found")
        elif condition.status != "True":
            problems.append(
                f"{kind}={condition.status} reason={condition.reason} msg={condition.message}"
            )
    for kind in must_not_be_true:
        condition = by_type.get(kind)
        if condition is not None and condition.status == "True":
            problems.append(f"{kind}=True reason={condition.reason} msg={condition.message}")
    return problems


@dataclass(frozen=True, slots=True)
class NodePoolHealth:
    """One NodePool's replicas and problems."""

    name: str
    ready_replicas: int
    desired_replicas: int
    problems: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LiveStatus:
    """A cluster's live state, or why it could not be read (``error``)."""

    cluster_name: str
    """The cluster file stem, as the API names clusters."""
    hosted_cluster: str
    namespace: str
    hc_phase: str | None = None
    ocp_version: str | None = None
    hc_problems: tuple[str, ...] = ()
    node_pools: tuple[NodePoolHealth, ...] = field(default=())
    error: str | None = None


def live_status(
    cluster_name: str,
    hosted_cluster: HostedClusterObservation,
    node_pools: Iterable[NodePoolObservation],
    *,
    node_pool_error: str | None = None,
) -> LiveStatus:
    """Combine the observations into a status, applying the health rules."""
    problems = condition_problems(
        hosted_cluster.conditions,
        must_be_true=HOSTED_CLUSTER_MUST_BE_TRUE,
        must_not_be_true=HOSTED_CLUSTER_MUST_NOT_BE_TRUE,
    )
    if node_pool_error is not None:
        problems.append(f"NodePool fetch failed: {node_pool_error}")
    pools = tuple(
        NodePoolHealth(
            name=pool.name,
            ready_replicas=pool.current_replicas,
            desired_replicas=pool.desired_replicas,
            problems=tuple(
                condition_problems(
                    pool.conditions,
                    must_be_true=NODE_POOL_MUST_BE_TRUE,
                    must_not_be_true=NODE_POOL_MUST_NOT_BE_TRUE,
                )
            ),
        )
        for pool in node_pools
    )
    return LiveStatus(
        cluster_name=cluster_name,
        hosted_cluster=hosted_cluster.name,
        namespace=hosted_cluster.namespace,
        hc_phase=hosted_cluster.phase,
        ocp_version=hosted_cluster.version,
        hc_problems=tuple(problems),
        node_pools=pools,
    )
