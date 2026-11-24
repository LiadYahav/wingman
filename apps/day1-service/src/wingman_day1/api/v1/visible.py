"""The cluster a route names, the merge requests, and each answer, as the user may know them.

Every ``/api/day1/clusters/{name}/...`` route finds its cluster here: a viewer
who names a KV cluster gets what a missing cluster gets, before anything else
is read (``domain/visibility.py``, ADR-0067). A viewer's cluster is found by
its name alone: ``site`` and ``mce`` are an admin's to send (ADR-0068), so a
viewer can never try MCE names against a cluster's.

A viewer's answer goes through :func:`shown`: its MCE, path and link fields
``null`` (``ADMIN_ONLY``) and its texts without the tree's MCE and KV names.

The approvals and the audit's merge requests are, for a viewer, the specs
project's and the day1 merge requests about a tenant's cluster (by the
cluster its title, footer or branch names, where the tree has that file),
and one merge request's diff is that cluster's file alone.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import BaseModel

from wingman_core.domain.git import FileDiff
from wingman_core.domain.mr_conventions import ResourceType
from wingman_core.domain.redaction import NO_REDACTION, Redactor
from wingman_core.domain.users import User
from wingman_core.web.viewer import all_for_viewer, for_viewer
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.approvals import Change, RepoKey
from wingman_day1.application.tree import Day1Tree
from wingman_day1.domain.errors import AmbiguousNameError, ResourceNotFoundError
from wingman_day1.domain.paths import CLUSTER_SUFFIX, ClusterRef, parse_hosted_clusters_path
from wingman_day1.domain.visibility import require_seen, sees_cluster, viewer_diffs
from wingman_day1.domain.workflows import provision_branch_stem


async def cluster_ref(
    context: Day1Context, user: User, name: str, site: str | None, mce: str | None
) -> ClusterRef:
    """Where the cluster is; ``ResourceNotFoundError`` for a viewer when it is a KV cluster.

    A viewer's is found by ``name`` alone, and a name two folders hold is
    ambiguous for them without the folders.
    """
    if user.is_admin:
        return await context.clusters.locate(name, site=site, mce=mce)
    try:
        ref = await context.clusters.locate(name)
    except AmbiguousNameError:
        raise AmbiguousNameError(
            f"cluster {name!r} is in more than one place in the day1 repo; ask an admin"
        ) from None
    require_seen(user, ref.name, mce=ref.mce)
    return ref


async def redactor(context: Day1Context, user: User) -> Redactor:
    """An admin's changes nothing; a viewer's hides each MCE's and KV cluster's name."""
    return NO_REDACTION if user.is_admin else (await context.sites.tree()).infrastructure


async def shown[M: BaseModel](context: Day1Context, user: User, model: M) -> M:
    """``model`` as ``user`` reads it: a viewer's without admin-only fields or the names."""
    return model if user.is_admin else for_viewer(model, await redactor(context, user))


async def all_shown[M: BaseModel](context: Day1Context, user: User, models: list[M]) -> list[M]:
    """:func:`shown` of each, with one read of the tree."""
    return models if user.is_admin else all_for_viewer(models, await redactor(context, user))


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
    """A specs merge request, or a day1 one about a cluster ``user`` may know of."""
    if change.repo is RepoKey.SPECS:
        return True
    name = _cluster_of(change)
    if name is None:
        return user.is_admin
    folders = [ref.mce for ref in tree.find(name)] or [""]
    return all(sees_cluster(user, name, mce=mce) for mce in folders)


async def seen_changes(context: Day1Context, user: User, changes: Iterable[Change]) -> list[Change]:
    """The merge requests ``user`` may know of: a viewer's, flavors' and tenants' clusters'."""
    if user.is_admin:
        return list(changes)
    tree = await context.sites.tree()
    return [change for change in changes if _sees(user, change, tree)]


async def seen_diffs(
    context: Day1Context, user: User, change: Change, diffs: Sequence[FileDiff]
) -> list[FileDiff]:
    """The diffs ``user`` reads of the merge request: a viewer's, its tenant cluster's file only.

    ``ResourceNotFoundError`` for a viewer when the merge request is not one
    they may know of, or touches a KV cluster's file.
    """
    if user.is_admin or change.repo is RepoKey.SPECS:
        return list(diffs)
    touched = [parse_hosted_clusters_path(p) for d in diffs for p in (d.old_path, d.new_path)]
    hidden = any(
        entry and not sees_cluster(user, entry.filename.removesuffix(CLUSTER_SUFFIX), mce=entry.mce)
        for entry in touched
    )
    if hidden or not await seen_changes(context, user, [change]):
        iid = change.pending.merge_request.ref.iid
        raise ResourceNotFoundError(f"merge request !{iid} was not found in the {change.repo} repo")
    return viewer_diffs(diffs, cluster=_cluster_of(change))
