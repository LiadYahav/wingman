"""``/api/day1/audit``: commits and MRs across the day1 and specs projects.

A viewer's audit is the flavors' and the tenants' clusters' (ADR-0068): the
specs project's commits and the day1 commits that changed a file in a
Customer MCE's ``hostedClusters/``, the merge requests about a flavor or a
tenant's cluster, and of one commit's diff the files a viewer may read (a
flavor's, a tenant cluster's by its file name). Every text they read names
no MCE, seed or KV cluster.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from wingman_core.web.auth import CurrentUser
from wingman_core.web.schemas import FileDiffOut
from wingman_day1.api.deps import Context
from wingman_day1.api.v1.audit_schemas import CommitRecordOut
from wingman_day1.api.v1.schemas import MRDetailOut
from wingman_day1.api.v1.visible import all_shown, seen_changes
from wingman_day1.application.approvals import Change, RepoKey
from wingman_day1.domain.errors import ResourceNotFoundError
from wingman_day1.domain.visibility import viewer_diffs

router = APIRouter(prefix="/api/day1/audit", tags=["audit"])

PerPage = Annotated[int, Query(ge=1, le=100)]
Page = Annotated[int, Query(ge=1, le=50)]


@router.get("/commits")
async def list_commits(
    context: Context, user: CurrentUser, per_page: PerPage = 50, page: Page = 1
) -> list[CommitRecordOut]:
    """Newest commits on both default branches; each says which repo it is from.

    A viewer's day1 commits are those that changed a tenant's cluster file.
    """
    folders = None if user.is_admin else (await context.sites.tree()).tenant_folders()
    commits = await context.audit.commits(per_page=per_page, page=page, day1_folders=folders)
    return await all_shown(context, user, [CommitRecordOut.of(c) for c in commits])


@router.get("/merge-requests")
async def list_merge_requests(
    context: Context, user: CurrentUser, per_page: PerPage = 50, page: Page = 1
) -> list[MRDetailOut]:
    """Newest MRs in both projects, any state; each says which repo it is from.

    A viewer's page has only those about a flavor or a tenant's cluster (ADR-0067,
    ADR-0068), so it may be shorter.
    """
    items = await context.audit.merge_requests(per_page=per_page, page=page)
    changes = await seen_changes(context, user, [Change(i.repo, i.change) for i in items])
    return await all_shown(context, user, [MRDetailOut.of(change) for change in changes])


@router.get("/commits/{repo}/{sha}/diff")
async def commit_diff(
    repo: RepoKey,
    sha: Annotated[str, Path(min_length=7, max_length=64, pattern=r"^[0-9a-f]+$")],
    context: Context,
    user: CurrentUser,
) -> list[FileDiffOut]:
    """What one commit changed.

    A viewer reads a day1 commit's tenant cluster files alone, by their file
    names; a commit that changed none is, for them, one that does not exist.
    """
    found, diffs = await context.audit.commit_diff(repo, sha)
    if not user.is_admin and found is RepoKey.DAY1:
        diffs = viewer_diffs(diffs)
        if not diffs:
            raise ResourceNotFoundError(
                f"commit {sha} is in neither the day1 nor the specs project"
            )
    return await all_shown(context, user, [FileDiffOut.of(d) for d in diffs])
