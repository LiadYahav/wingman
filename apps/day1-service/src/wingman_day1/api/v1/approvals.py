"""``/api/day1/approvals``: Wingman MRs in the day1 and specs projects.

An MR is ``(repo, iid)``. ``repo`` defaults to ``day1`` (this is the day1
service), which is what the audit page's expand calls without one; the
legacy route required it and answered 422.

Merging a flavor's MR gives the flavor a new version: Wingman then opens one
MR per cluster that follows it (ADR-0044), and before the merge the review
page shows what that will open (``GET /{iid}/rollout``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from wingman_core.domain.mr_conventions import ResourceType
from wingman_core.web.auth import AdminUser, CurrentUser
from wingman_day1.api.deps import Context
from wingman_day1.api.v1.schemas import (
    ApprovalDetailOut,
    ApprovalRolloutOut,
    ApproveIn,
    FileDiffOut,
    MRDetailOut,
    UpdateMRIn,
)
from wingman_day1.application.approvals import Change, RepoKey
from wingman_day1.application.rollouts import RolloutPreview
from wingman_day1.domain.rollout import RolloutTrigger

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
    """Approve and merge the reviewed commit. 403 for the requester; 409 if the branch moved.

    A flavor's MR, merged, starts its rollout: one MR per cluster that follows it.
    """
    change = await context.approvals.approve(repo, iid, sha=body.sha, approver=user)
    flavor = _flavor(change)
    if flavor is not None:
        context.rollouts.start(flavor, RolloutTrigger.MERGE)
    return MRDetailOut.of(change)


@router.get("/{iid}/rollout")
async def approval_rollout(
    iid: Iid, context: Context, user: CurrentUser, repo: Repo = RepoKey.DAY1
) -> ApprovalRolloutOut:
    """What merging this MR opens: one MR per cluster of the flavor it gives a new version."""
    change, _ = await context.approvals.get(repo, iid)
    flavor = _flavor(change)
    metadata = change.pending.metadata
    if flavor is None or metadata is None:
        return ApprovalRolloutOut.of(
            RolloutPreview(False, "this merge request does not change a flavor", "", None, None)
        )
    return ApprovalRolloutOut.of(
        await context.rollouts.preview_merge_request(
            flavor, action=metadata.action, sha=change.pending.merge_request.sha
        )
    )


def _flavor(change: Change) -> str | None:
    """The flavor a specs MR creates, updates or deletes; ``None`` for any other MR."""
    metadata = change.pending.metadata
    if change.repo is not RepoKey.SPECS or metadata is None:
        return None
    if metadata.resource_type is not ResourceType.SPEC or not metadata.resource_name:
        return None
    return metadata.resource_name


@router.post("/{iid}/reject")
async def reject(
    iid: Iid, context: Context, user: AdminUser, repo: Repo = RepoKey.DAY1
) -> MRDetailOut:
    """Close the MR without merging."""
    return MRDetailOut.of(await context.approvals.reject(repo, iid))
