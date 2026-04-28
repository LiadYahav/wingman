"""Day1 audit routes — commit and MR history across day1 + specs repos."""

from __future__ import annotations

from fastapi import APIRouter, Query
from wingman_shared.models import CommitRecord, FileDiff, MRDetail

from ..dependencies import AuditServiceDep, CurrentUser

router = APIRouter(prefix="/api/day1/audit", tags=["audit"])


@router.get("/commits", response_model=list[CommitRecord])
async def list_commits(
    audit_svc: AuditServiceDep,
    user: CurrentUser,
    per_page: int = Query(default=50, ge=1, le=100),
    page: int = Query(default=1, ge=1),
) -> list[CommitRecord]:
    return await audit_svc.list_commits(per_page=per_page, page=page)


@router.get("/merge-requests", response_model=list[MRDetail])
async def list_merge_requests(
    audit_svc: AuditServiceDep,
    user: CurrentUser,
    per_page: int = Query(default=50, ge=1, le=100),
    page: int = Query(default=1, ge=1),
) -> list[MRDetail]:
    return await audit_svc.list_mrs(per_page=per_page, page=page)


@router.get("/commits/{repo}/{commit_id}/diff", response_model=list[FileDiff])
async def get_commit_diff(
    repo: str,
    commit_id: str,
    audit_svc: AuditServiceDep,
    user: CurrentUser,
) -> list[FileDiff]:
    """Get file diffs for a commit. repo must be 'day1' or 'specs'."""
    return await audit_svc.get_commit_diff(repo, commit_id)
