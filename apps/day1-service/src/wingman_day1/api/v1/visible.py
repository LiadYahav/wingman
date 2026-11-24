"""The cluster a route names, and the merge requests, as the signed-in user may know of them.

Every ``/api/day1/clusters/{name}/...`` route finds its cluster here: a viewer
who names a KV cluster gets what a missing cluster gets, before anything else
is read (``domain/visibility.py``, ADR-0067). The approvals and the audit's
merge requests leave out, for a viewer, every day1 merge request about a KV
cluster: by the cluster its title, footer or branch names, where the tree has
that file, and for one merge request by the paths its diff touches.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from wingman_core.domain.git import FileDiff
from wingman_core.domain.mr_conventions import ResourceType
from wingman_core.domain.users import User
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.approvals import Change, RepoKey
from wingman_day1.application.tree import Day1Tree
from wingman_day1.domain.errors import ResourceNotFoundError
from wingman_day1.domain.paths import CLUSTER_SUFFIX, ClusterRef, parse_hosted_clusters_path
from wingman_day1.domain.visibility import require_seen, sees_cluster
from wingman_day1.domain.workflows import provision_branch_stem


async def cluster_ref(
    context: Day1Context, user: User, name: str, site: str | None, mce: str | None
) -> ClusterRef:
    """Where the cluster is; ``ResourceNotFoundError`` for a viewer when it is a KV cluster."""
    ref = await context.clusters.locate(name, site=site, mce=mce)
    require_seen(user, ref.name, mce=ref.mce)
    return ref


def _cluster_of(change: Change) -> str | None:
    """The cluster a day1 merge request is about; ``None`` for any other."""
    if change.repo is not RepoKey.DAY1:
        return None
    pending = change.pending
    for named in (pending.metadata, pending.title):
        if named is not None and named.resource_type is ResourceType.CLUSTER:
            return named.resource_name
    return provision_branch_stem(pending.merge_request.source_branch)


def _sees(user: User, change: Change, tree: Day1Tree) -> bool:
    name = _cluster_of(change)
    if name is None:
        return True
    folders = [ref.mce for ref in tree.find(name)] or [""]
    return all(sees_cluster(user, name, mce=mce) for mce in folders)


async def seen_changes(context: Day1Context, user: User, changes: Iterable[Change]) -> list[Change]:
    """The merge requests ``user`` may know of: a viewer's has none about a KV cluster."""
    if user.is_admin:
        return list(changes)
    tree = await context.sites.tree()
    return [change for change in changes if _sees(user, change, tree)]


async def require_seen_change(
    context: Day1Context, user: User, change: Change, diffs: Sequence[FileDiff]
) -> None:
    """Raise for a viewer when the merge request is about, or touches, a KV cluster's file."""
    if user.is_admin:
        return
    touched = [parse_hosted_clusters_path(p) for d in diffs for p in (d.old_path, d.new_path)]
    hidden = any(
        entry and not sees_cluster(user, entry.filename.removesuffix(CLUSTER_SUFFIX), mce=entry.mce)
        for entry in touched
    )
    if hidden or not await seen_changes(context, user, [change]):
        iid = change.pending.merge_request.ref.iid
        raise ResourceNotFoundError(f"merge request !{iid} was not found in the {change.repo} repo")
