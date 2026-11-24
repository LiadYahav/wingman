"""``/api/day1/approvals``: Wingman MRs in the day1 and specs projects.

An MR is ``(repo, iid)``. ``repo`` defaults to ``day1`` (this is the day1
service), which is what the audit page's expand calls without one; the
legacy route required it and answered 422.

Merging a flavor's MR gives the flavor a new version: Wingman then opens one
MR per cluster that follows it (ADR-0044), and before the merge the review
page shows what that will open (``GET /{iid}/rollout``).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Path, Query

from wingman_core.domain.mr_conventions import ResourceType
from wingman_core.domain.users import User
from wingman_core.web.auth import AdminUser, CurrentUser
from wingman_core.web.schemas import FileDiffOut
from wingman_day1.api.deps import Context
from wingman_day1.api.v1.approvals_schemas import (
    ApprovalDetailOut,
    ApprovalRolloutOut,
    ApproveIn,
    UpdateMRIn,
)
from wingman_day1.api.v1.schemas import MRDetailOut
from wingman_day1.api.v1.visible import all_shown, seen_changes, seen_diffs, shown
from wingman_day1.application.approvals import Change, RepoKey
from wingman_day1.application.rollouts import RolloutPreview
from wingman_day1.domain.rollout import RolloutTrigger
from wingman_day1.domain.visibility import seen

router = APIRouter(prefix="/api/day1/approvals", tags=["approvals"])

Repo = Annotated[RepoKey, Query(description="day1 (default) or specs")]
Iid = Annotated[int, Path(ge=1)]


@router.get("")
async def list_approvals(context: Context, user: CurrentUser) -> list[MRDetailOut]:
    """Open Wingman MRs in both projects, whatever branch they target.

    A viewer's list is the flavors' and the tenants' clusters', without an
    infrastructure name (ADR-0067, ADR-0068).
    """
    changes = await seen_changes(context, user, await context.approvals.pending())
    return await all_shown(context, user, [MRDetailOut.of(change) for change in changes])


@router.get("/{iid}")
async def get_approval(
    iid: Iid, context: Context, user: CurrentUser, repo: Repo = RepoKey.DAY1
) -> ApprovalDetailOut:
    """One MR and its diff; ``mr.sha`` is what an approval must name.

    A viewer gets a 404 for one they may not know of, and of a day1 MR's diff
    the cluster's own file alone, named by its file name (ADR-0068).
    """
    change, diffs = await context.approvals.get(repo, iid)
    shown_diffs = await seen_diffs(context, user, change, diffs)
    detail = ApprovalDetailOut(
        mr=MRDetailOut.of(change), diffs=[FileDiffOut.of(d) for d in shown_diffs]
    )
    return await shown(context, user, detail)


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
    """What merging this MR opens: one MR per cluster of the flavor it gives a new version.

    A viewer's names no KV cluster and no MCE (ADR-0068).
    """
    change, diffs = await context.approvals.get(repo, iid)
    await seen_diffs(context, user, change, diffs)
    flavor = _flavor(change)
    metadata = change.pending.metadata
    if flavor is None or metadata is None:
        return ApprovalRolloutOut.of(
            RolloutPreview(False, "this merge request does not change a flavor", "", None, None)
        )
    preview = await context.rollouts.preview_merge_request(
        flavor, action=metadata.action, sha=change.pending.merge_request.sha
    )
    return await shown(context, user, ApprovalRolloutOut.of(_visible(preview, user)))


def _visible(preview: RolloutPreview, user: User) -> RolloutPreview:
    """A viewer's preview lists no KV cluster (ADR-0067); its counts stay the flavor's."""
    if user.is_admin:
        return preview
    return replace(
        preview,
        needs_decision=tuple(seen(user, preview.needs_decision, lambda c: c.ref)),
        rolls_nodes=tuple(seen(user, preview.rolls_nodes, lambda c: c.ref)),
        removes_configs=tuple(seen(user, preview.removes_configs, lambda c: c.ref)),
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
