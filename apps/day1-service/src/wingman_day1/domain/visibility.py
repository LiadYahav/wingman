"""What a viewer may know of the platform: tenants' clusters, never the infrastructure (ADR-0067).

Seeds, KV clusters and the MCE lists are an admin's (the user, 2026-11-23:
"no viewer should know"). Day1 enforces it on every read a viewer may make,
before anything is read for it; the web only follows:

- a KV cluster is answered as a missing cluster would be (404, the same words);
- a list a viewer reads leaves every KV cluster out, as if it were not there;
- the lists of sites and MCEs, placement and Inventory Management are
  ``AdminUser`` reads, a viewer's ``403`` (``api/v1/sites.py``,
  ``placement.py``, ``inventory.py``).

A tenant's cluster still says which site and MCE it is on: that is where it
lives, and how its status is read.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from wingman_core.domain.cluster_kinds import HostedClusterKind, hosted_cluster_kind
from wingman_core.domain.users import User
from wingman_day1.domain.errors import ResourceNotFoundError
from wingman_day1.domain.paths import ClusterRef


def sees_cluster(user: User, name: str, *, mce: str) -> bool:
    """Whether ``user`` may know of the cluster file ``name`` under ``mce`` (empty: unknown)."""
    return user.is_admin or hosted_cluster_kind(name, mce=mce) is HostedClusterKind.TENANT


def require_seen(user: User, name: str, *, mce: str) -> None:
    """Raise what a missing cluster raises when ``user`` may not know of it."""
    if not sees_cluster(user, name, mce=mce):
        raise ResourceNotFoundError(f"cluster {name!r} does not exist in the day1 repo")


def seen[T](user: User, items: Iterable[T], ref: Callable[[T], ClusterRef]) -> list[T]:
    """The items whose cluster ``user`` may know of, in their order."""
    return [item for item in items if sees_cluster(user, ref(item).name, mce=ref(item).mce)]
