"""MCE-level routes (live Kubernetes API)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from ..dependencies import ClusterStatusServiceDep, CurrentUser, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/day1/mces", tags=["mces"])


@router.get("/{mce}/infraenvs", response_model=list[str])
async def list_mce_infraenvs(
    mce: str,
    user: CurrentUser,
    status_svc: ClusterStatusServiceDep,
) -> list[str]:
    """List InfraEnv names available on the given MCE hosting cluster."""
    settings = get_settings()
    try:
        return await asyncio.to_thread(
            status_svc.list_infraenvs, mce, settings.MCE_INFRAENV_NAMESPACE
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Failed to list infraenvs for MCE '%s': %s", mce, exc)
        raise HTTPException(status_code=502, detail=f"MCE API error: {exc}") from exc
