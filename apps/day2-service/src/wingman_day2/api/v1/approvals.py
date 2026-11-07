"""Approvals and audit. An MR is addressed by ``{team}/{iid}``, never by number alone (ADR-0007)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from wingman_core.web.auth import AdminUser, CurrentUser
from wingman_day2.api.v1.dependencies import Services
from wingman_day2.api.v1.schemas import (
    ApprovalDetailOut,
    ApproveBody,
    CommitRecordOut,
    EditMergeRequestBody,
    FileDiffOut,
    MRDetailOut,
)
from wingman_day2.application.approvals import FileEdit

router = APIRouter(prefix="/api/day2", tags=["approvals"])


@router.get("/approvals")
async def list_approvals(user: CurrentUser, day2: Services) -> list[MRDetailOut]:
    """Open Wingman MRs across every team repo, newest first."""
    return [MRDetailOut.of_change(c.team.name, c.change) for c in await day2.approvals.pending()]


@router.get("/approvals/{team}/{iid}")
async def get_approval(team: str, iid: int, user: CurrentUser, day2: Services) -> ApprovalDetailOut:
    """One MR and its diff."""
    change, diffs = await day2.approvals.detail(team, iid)
    return ApprovalDetailOut(
        mr=MRDetailOut.of_change(team, change.change), diffs=[FileDiffOut.of(d) for d in diffs]
    )


@router.put("/approvals/{team}/{iid}")
async def edit_approval(
    team: str, iid: int, body: EditMergeRequestBody, user: AdminUser, day2: Services
) -> ApprovalDetailOut:
    """Push edits of files the MR changes onto its branch (409 if a file moved on)."""
    change, diffs = await day2.approvals.edit(
        team,
        iid,
        [FileEdit(f.path, f.content, f.last_commit_id) for f in body.files],
        body.message,
        user,
    )
    return ApprovalDetailOut(
        mr=MRDetailOut.of_change(team, change.change), diffs=[FileDiffOut.of(d) for d in diffs]
    )


@router.post("/approvals/{team}/{iid}/approve")
async def approve(
    team: str, iid: int, body: ApproveBody, user: AdminUser, day2: Services
) -> MRDetailOut:
    """Approve and merge the reviewed commit (403 for your own change, 409 if it moved)."""
    return MRDetailOut.of(
        team, await day2.approvals.approve(team, iid, sha=body.sha, approver=user)
    )


@router.post("/approvals/{team}/{iid}/reject")
async def reject(team: str, iid: int, user: AdminUser, day2: Services) -> MRDetailOut:
    """Close without merging."""
    return MRDetailOut.of(team, await day2.approvals.reject(team, iid))


@router.get("/audit/commits")
async def audit_commits(
    user: CurrentUser,
    day2: Services,
    per_page: int = Query(default=50, ge=1, le=100),
    page: int = Query(default=1, ge=1, le=20),
) -> list[CommitRecordOut]:
    """Commits across team repos, newest first."""
    return [
        CommitRecordOut.of(c.team, c.commit)
        for c in await day2.audit.commits(per_page=per_page, page=page)
    ]


@router.get("/audit/merge-requests")
async def audit_merge_requests(
    user: CurrentUser,
    day2: Services,
    per_page: int = Query(default=50, ge=1, le=100),
    page: int = Query(default=1, ge=1, le=20),
) -> list[MRDetailOut]:
    """Wingman MRs in any state across team repos, newest update first."""
    return [
        MRDetailOut.of(m.team, m.merge_request)
        for m in await day2.audit.merge_requests(per_page=per_page, page=page)
    ]


@router.get("/audit/commits/{sha}/diff")
async def audit_commit_diff(
    sha: str, user: CurrentUser, day2: Services, team: str | None = Query(default=None)
) -> list[FileDiffOut]:
    """What a commit changed, in the team repo that has it."""
    _, diffs = await day2.audit.commit_diff(sha, team=team)
    return [FileDiffOut.of(d) for d in diffs]
