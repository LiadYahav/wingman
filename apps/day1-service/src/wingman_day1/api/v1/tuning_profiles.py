"""``/api/day1/tuning-profiles``: what a nodepool's ``tuning_config`` may name (ADR-0061)."""

from __future__ import annotations

from fastapi import APIRouter

from wingman_core.web.auth import CurrentUser
from wingman_day1.api.deps import Context
from wingman_day1.api.v1.tuning_profiles_schemas import TuningProfilesOut

router = APIRouter(prefix="/api/day1/tuning-profiles", tags=["tuning-profiles"])


@router.get("")
async def tuning_profiles(context: Context, user: CurrentUser) -> TuningProfilesOut:
    """The shared profiles in ``tuning/``, their per-cluster variants, and the files that fail."""
    return TuningProfilesOut.of(await context.machine_configs.tuning())
