"""Which destinations a viewer may know of: never an MCE, a seed or a KV cluster (ADR-0067).

day2 lists every destination day1 and the team repos name, the MCE hubs and
their hosted clusters among them. A seed is an MCE-level folder of day1 and a
KV cluster a hosted cluster in it (``wingman_core.domain.cluster_kinds``), so
for a viewer the destination list has no ``mce`` destination at all and no
hosted cluster that is a KV cluster, and naming one answers what an unknown
destination answers. The hub and the UPI clusters are not day1's MCE folders
and stay; an admin sees everything.
"""

from __future__ import annotations

from wingman_core.domain.cluster_kinds import HostedClusterKind, hosted_cluster_kind
from wingman_core.domain.users import User
from wingman_day2.domain.clusters import ClusterKind, ClusterRef


def sees_destination(user: User, ref: ClusterRef) -> bool:
    """Whether ``user`` may know of the destination ``ref``."""
    if user.is_admin:
        return True
    if ref.kind is ClusterKind.MCE:
        return False
    if ref.kind is ClusterKind.HOSTED:
        return hosted_cluster_kind(ref.name, mce=ref.mce) is HostedClusterKind.TENANT
    return True
