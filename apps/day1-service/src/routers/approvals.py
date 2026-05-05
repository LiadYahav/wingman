"""Day1 approval routes — MR review and approval workflow."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from wingman_shared.models import MRDetail, UpdateMRRequest

from ..dependencies import AdminUser, ApprovalServiceDep, CurrentUser

router = APIRouter(prefix="/api/day1/approvals", tags=["approvals"])

RepoType = Literal["day1", "specs"]


@router.get("", response_model=list[MRDetail])
async def list_approvals(
    approval_svc: ApprovalServiceDep,
    user: CurrentUser,
) -> list[MRDetail]:
    return await approval_svc.list_open_mrs()


@router.get("/{mr_iid}", response_model=dict)
async def get_approval(
    mr_iid: int,
    repo: Annotated[RepoType, Query(description="Repository type: day1 or specs")],
    approval_svc: ApprovalServiceDep,
    user: CurrentUser,
) -> dict:
    return await approval_svc.get_mr_detail(mr_iid, repo)


@router.put("/{mr_iid}", response_model=dict)
async def update_mr(
    mr_iid: int,
    repo: Annotated[RepoType, Query(description="Repository type: day1 or specs")],
    body: UpdateMRRequest,
    approval_svc: ApprovalServiceDep,
    user: AdminUser,
) -> dict:
    return await approval_svc.update_mr(mr_iid, repo, body, user)


@router.post("/{mr_iid}/approve", response_model=MRDetail)
async def approve_mr(
    mr_iid: int,
    repo: Annotated[RepoType, Query(description="Repository type: day1 or specs")],
    approval_svc: ApprovalServiceDep,
    user: AdminUser,
) -> MRDetail:
    return await approval_svc.approve_mr(mr_iid, repo, user)


@router.post("/{mr_iid}/reject", response_model=MRDetail)
async def reject_mr(
    mr_iid: int,
    repo: Annotated[RepoType, Query(description="Repository type: day1 or specs")],
    approval_svc: ApprovalServiceDep,
    user: AdminUser,
) -> MRDetail:
    return await approval_svc.reject_mr(mr_iid, repo, user)
