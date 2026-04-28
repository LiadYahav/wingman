"""Day2 approval routes."""

from __future__ import annotations

from fastapi import APIRouter
from wingman_shared.models import MRDetail, UpdateMRRequest

from ..dependencies import AdminUser, ApprovalServiceDep, CurrentUser

router = APIRouter(prefix="/api/day2/approvals", tags=["approvals"])


@router.get("", response_model=list[MRDetail])
async def list_approvals(svc: ApprovalServiceDep, user: CurrentUser) -> list[MRDetail]:
    return await svc.list_open_mrs()


@router.get("/{mr_iid}", response_model=dict)
async def get_approval(mr_iid: int, svc: ApprovalServiceDep, user: CurrentUser) -> dict:
    return await svc.get_mr_detail(mr_iid)


@router.put("/{mr_iid}", response_model=dict)
async def update_mr(
    mr_iid: int, body: UpdateMRRequest, svc: ApprovalServiceDep, user: AdminUser
) -> dict:
    return await svc.update_mr(mr_iid, body, user)


@router.post("/{mr_iid}/approve", response_model=MRDetail)
async def approve_mr(mr_iid: int, svc: ApprovalServiceDep, user: AdminUser) -> MRDetail:
    return await svc.approve_mr(mr_iid, user)


@router.post("/{mr_iid}/reject", response_model=MRDetail)
async def reject_mr(mr_iid: int, svc: ApprovalServiceDep, user: AdminUser) -> MRDetail:
    return await svc.reject_mr(mr_iid, user)
