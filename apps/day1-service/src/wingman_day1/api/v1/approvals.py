"""``/api/day1/approvals``: Wingman MRs in the day1 and specs projects.

An MR is ``(repo, iid)``. ``repo`` defaults to ``day1`` (this is the day1
service), which is what the audit page's expand calls without one; the
legacy route required it and answered 422.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from wingman_core.web.auth import AdminUser, CurrentUser
from wingman_day1.api.deps import Context
from wingman_day1.api.v1.schemas import (
    ApprovalDetailOut,
    ApproveIn,
    FileDiffOut,
    MRDetailOut,
    UpdateMRIn,
)
from wingman_day1.application.approvals import RepoKey

router = APIRouter(prefix="/api/day1/approvals", tags=["approvals"])

Repo = Annotated[RepoKey, Query(description="day1 (default) or specs")]
Iid = Annotated[int, Path(ge=1)]


@router.get("")
async def list_approvals(context: Context, user: CurrentUser) -> list[MRDetailOut]:
    """Open Wingman MRs in both projects, whatever branch they target."""
    return [MRDetailOut.of(change) for change in await context.approvals.pending()]


@router.get("/{iid}")
async def get_approval(
    iid: Iid, context: Context, user: CurrentUser, repo: Repo = RepoKey.DAY1
) -> ApprovalDetailOut:
    """One MR and its diff; ``mr.sha`` is what an approval must name."""
    change, diffs = await context.approvals.get(repo, iid)
    return ApprovalDetailOut(mr=MRDetailOut.of(change), diffs=[FileDiffOut.of(d) for d in diffs])


@router.put("/{iid}")
async def update_approval(
    iid: Iid, body: UpdateMRIn, context: Context, user: AdminUser, repo: Repo = RepoKey.DAY1
) -> ApprovalDetailOut:
    """Commit edited files on top of the MR's branch (never a force-push)."""
    change, diffs = await context.approvals.update(
        repo,
        iid,
        {f.path: f.content for f in body.files},
        user=user,
        sha=body.sha,
        message=body.message,
    )
    return ApprovalDetailOut(mr=MRDetailOut.of(change), diffs=[FileDiffOut.of(d) for d in diffs])


@router.post("/{iid}/approve")
async def approve(
    iid: Iid, body: ApproveIn, context: Context, user: AdminUser, repo: Repo = RepoKey.DAY1
) -> MRDetailOut:
    """Approve and merge the reviewed commit. 403 for the requester; 409 if the branch moved."""
    return MRDetailOut.of(await context.approvals.approve(repo, iid, sha=body.sha, approver=user))


@router.post("/{iid}/reject")
async def reject(
    iid: Iid, context: Context, user: AdminUser, repo: Repo = RepoKey.DAY1
) -> MRDetailOut:
    """Close the MR without merging."""
    return MRDetailOut.of(await context.approvals.reject(repo, iid))
