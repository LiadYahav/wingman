"""A NodePool's scale-down policy: which servers a scale-down removes first (ADR-0062).

update-nodepool ranks a shrinking NodePool's Machines by a policy and marks the
first ones before it lowers the replicas, so CAPI removes exactly those. The
policy is, in this order (the workflow's rule):

1. the run's own ``scale_down_policy``, for that run only;
2. the NodePool's ``redbull.io/scale-down-policy``, which the
   hostedclusters-setup chart renders from the ``nodepool[]`` entry's
   ``annotations`` (team-redbull/helm-charts-hostedclusters-setup PR #4);
3. none: nothing is marked, and CAPI picks at random.

Under every policy, Machines CAPI counts unhealthy go first, then Nodes that
are missing, NotReady or cordoned. The values are the workflow's
``ScaleDownPolicy``, and it refuses any other:

- ``fewest-pods``: the fewest workload pods, the least for the drain to move;
- ``least-requested``: the lowest share of CPU or memory its pods request;
- ``least-utilized``: the lowest live CPU or memory use, read from the hosted
  cluster's metrics API (``metrics.k8s.io``); without one the run fails
  (``NodeMetricsUnavailableError``).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, cast

SCALE_DOWN_POLICY: Final = "redbull.io/scale-down-policy"
"""The key update-nodepool reads off a NodePool to choose the servers a scale-down removes."""
ANNOTATIONS: Final = "annotations"
"""The ``nodepool[]`` entry's map the chart renders onto its NodePool."""
INPUT: Final = "scale_down_policy"
"""The per-run override's field."""


class ScaleDownPolicy(StrEnum):
    """The policies update-nodepool knows (its ``ScaleDownPolicy``)."""

    FEWEST_PODS = "fewest-pods"
    LEAST_REQUESTED = "least-requested"
    LEAST_UTILIZED = "least-utilized"


POLICIES: Final = tuple(p.value for p in ScaleDownPolicy)


def policy_of(entry: Mapping[str, object]) -> str | None:
    """The policy a file entry's ``annotations`` name, as written; ``None`` without one.

    The chart renders an entry's annotations onto its NodePool, where
    update-nodepool reads the key (a label or an annotation set by hand on
    the MCE is read there too; the file cannot show it). The value is not
    checked here: the workflow refuses one it does not know.
    """
    annotations = entry.get(ANNOTATIONS)
    if not isinstance(annotations, Mapping):
        return None
    value = cast("Mapping[str, object]", annotations).get(SCALE_DOWN_POLICY)
    return None if value is None else str(value)
