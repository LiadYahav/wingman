"""What a viewer may know of the platform: tenants' clusters, never the infrastructure.

Seeds, KV clusters and the MCEs are an admin's (the user, 2026-11-23: "no
viewer should know"; ADR-0067). Day1 enforces it on every read a viewer may
make, before anything is read for it; the web only follows:

- a KV cluster is answered as a missing cluster would be (404, the same words);
- a list a viewer reads leaves every KV cluster out, as if it were not there;
- the lists of sites and MCEs, placement and Inventory Management are
  ``AdminUser`` reads, a viewer's ``403`` (``api/v1/sites.py``,
  ``placement.py``, ``inventory.py``).

A tenant's cluster says its site, the place in its own name, but never its
MCE (ADR-0068): a viewer's answers leave every MCE, file path and link into
the tree ``null``, and their free text names no MCE, seed or KV cluster
(``wingman_core.domain.redaction``). Of the day1 repo's files a viewer reads
a tenant cluster's alone, named by its file name (:func:`viewer_diffs`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace
from typing import Final

from wingman_core.domain.cluster_kinds import HostedClusterKind, hosted_cluster_kind
from wingman_core.domain.git import FileDiff, RepoPath
from wingman_core.domain.users import User
from wingman_day1.domain.errors import ResourceNotFoundError
from wingman_day1.domain.paths import ClusterRef, parse_hosted_clusters_path

UNREAD_STATUS: Final = "the cluster's live status could not be read"
"""A viewer's ``error`` for a failed hub read: the hub's own words name it (ADR-0068)."""


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


def tenant_file(path: RepoPath) -> ClusterRef | None:
    """The tenant's cluster ``path`` is the file of; ``None`` for any other day1 file."""
    entry = parse_hosted_clusters_path(path)
    ref = entry.cluster if entry is not None else None
    return ref if ref is not None and ref.kind is HostedClusterKind.TENANT else None


def viewer_diffs(diffs: Sequence[FileDiff], *, cluster: str | None = None) -> list[FileDiff]:
    """The day1 diffs a viewer reads: tenant clusters' files (``cluster``'s alone, when given).

    Each keeps its text and is named by its file name alone,
    ``ocp4-prod-lark-site1.yaml``: the folders are the site's and the MCE's.
    """
    shown: list[FileDiff] = []
    for diff in diffs:
        refs = {tenant_file(diff.old_path), tenant_file(diff.new_path)}
        if None in refs or (cluster is not None and {r.name for r in refs if r} != {cluster}):
            continue
        shown.append(
            replace(
                diff,
                old_path=RepoPath(diff.old_path.name),
                new_path=RepoPath(diff.new_path.name),
            )
        )
    return shown
