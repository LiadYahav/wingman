"""Day1 approval routes — MR review and approval workflow."""

from __future__ import annotations

from fastapi import APIRouter
from wingman_shared.models import MRDetail, UpdateMRRequest

from ..dependencies import AdminUser, ApprovalServiceDep, CurrentUser

router = APIRouter(prefix="/api/day1/approvals", tags=["approvals"])


@router.get("", response_model=list[MRDetail])
async def list_approvals(
    approval_svc: ApprovalServiceDep,
    user: CurrentUser,
) -> list[MRDetail]:
    return await approval_svc.list_open_mrs()


@router.get("/{mr_iid}", response_model=dict)
async def get_approval(
    mr_iid: int,
    approval_svc: ApprovalServiceDep,
    user: CurrentUser,
) -> dict:
    return await approval_svc.get_mr_detail(mr_iid)


@router.put("/{mr_iid}", response_model=dict)
async def update_mr(
    mr_iid: int,
    body: UpdateMRRequest,
    approval_svc: ApprovalServiceDep,
    user: AdminUser,
) -> dict:
    return await approval_svc.update_mr(mr_iid, body, user)


@router.post("/{mr_iid}/approve", response_model=MRDetail)
async def approve_mr(
    mr_iid: int,
    approval_svc: ApprovalServiceDep,
    user: AdminUser,
) -> MRDetail:
    return await approval_svc.approve_mr(mr_iid, user)


@router.post("/{mr_iid}/reject", response_model=MRDetail)
async def reject_mr(
    mr_iid: int,
    approval_svc: ApprovalServiceDep,
    user: AdminUser,
) -> MRDetail:
    return await approval_svc.reject_mr(mr_iid, user)
