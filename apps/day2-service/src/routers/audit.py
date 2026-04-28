"""Day2 audit routes."""

from __future__ import annotations

from fastapi import APIRouter, Query
from wingman_shared.models import CommitRecord, FileDiff, MRDetail

from ..dependencies import AuditServiceDep, CurrentUser

router = APIRouter(prefix="/api/day2/audit", tags=["audit"])


@router.get("/commits", response_model=list[CommitRecord])
async def list_commits(
    svc: AuditServiceDep,
    user: CurrentUser,
    per_page: int = Query(default=50, ge=1, le=100),
    page: int = Query(default=1, ge=1),
) -> list[CommitRecord]:
    return await svc.list_commits(per_page=per_page, page=page)


@router.get("/merge-requests", response_model=list[MRDetail])
async def list_merge_requests(
    svc: AuditServiceDep,
    user: CurrentUser,
    per_page: int = Query(default=50, ge=1, le=100),
    page: int = Query(default=1, ge=1),
) -> list[MRDetail]:
    return await svc.list_mrs(per_page=per_page, page=page)


@router.get("/commits/{commit_id}/diff", response_model=list[FileDiff])
async def get_commit_diff(
    commit_id: str,
    svc: AuditServiceDep,
    user: CurrentUser,
) -> list[FileDiff]:
    """Get file diffs for a commit in the day2 repo."""
    return await svc.get_commit_diff(commit_id)
