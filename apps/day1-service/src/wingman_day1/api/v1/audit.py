"""``/api/day1/audit``: commits and MRs across the day1 and specs projects."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from wingman_core.web.auth import CurrentUser
from wingman_core.web.schemas import FileDiffOut
from wingman_day1.api.deps import Context
from wingman_day1.api.v1.audit_schemas import CommitRecordOut
from wingman_day1.api.v1.schemas import MRDetailOut
from wingman_day1.application.approvals import Change, RepoKey

router = APIRouter(prefix="/api/day1/audit", tags=["audit"])

PerPage = Annotated[int, Query(ge=1, le=100)]
Page = Annotated[int, Query(ge=1, le=50)]


@router.get("/commits")
async def list_commits(
    context: Context, user: CurrentUser, per_page: PerPage = 50, page: Page = 1
) -> list[CommitRecordOut]:
    """Newest commits on both default branches; each says which repo it is from."""
    return [
        CommitRecordOut.of(c) for c in await context.audit.commits(per_page=per_page, page=page)
    ]


@router.get("/merge-requests")
async def list_merge_requests(
    context: Context, user: CurrentUser, per_page: PerPage = 50, page: Page = 1
) -> list[MRDetailOut]:
    """Newest MRs in both projects, any state; each says which repo it is from."""
    return [
        MRDetailOut.of(Change(item.repo, item.change))
        for item in await context.audit.merge_requests(per_page=per_page, page=page)
    ]


@router.get("/commits/{repo}/{sha}/diff")
async def commit_diff(
    repo: RepoKey,
    sha: Annotated[str, Path(min_length=7, max_length=64, pattern=r"^[0-9a-f]+$")],
    context: Context,
    user: CurrentUser,
) -> list[FileDiffOut]:
    """What one commit changed."""
    return [FileDiffOut.of(d) for d in await context.audit.commit_diff(repo, sha)]
