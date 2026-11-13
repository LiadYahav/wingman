"""``/api/day1/machine-configs``: what a nodepool's ``configs`` may name (ADR-0027)."""

from __future__ import annotations

from fastapi import APIRouter

from wingman_core.web.auth import CurrentUser
from wingman_day1.api.deps import Context
from wingman_day1.api.v1.machine_configs_schemas import MachineConfigsOut

router = APIRouter(prefix="/api/day1/machine-configs", tags=["machine-configs"])


@router.get("")
async def machine_configs(context: Context, user: CurrentUser) -> MachineConfigsOut:
    """Static configs, hardware types and the nodepool defaults, from ``mc-files/``."""
    return MachineConfigsOut.of(await context.machine_configs.overview())
