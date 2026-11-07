"""Sites and MCEs (read-only, ADR-0018) and the InfraEnvs on an MCE hub.

``POST /api/day1/sites`` and ``POST /api/day1/sites/{site}/mces`` are gone:
Wingman no longer creates sites or MCEs (they answer 405).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from wingman_core.web.auth import CurrentUser
from wingman_day1.api.deps import Context, Status
from wingman_day1.api.v1.schemas import MceOut

sites_router = APIRouter(prefix="/api/day1/sites", tags=["sites"])
mces_router = APIRouter(prefix="/api/day1/mces", tags=["mces"])

Name = Annotated[str, Path(min_length=1, max_length=63)]


@sites_router.get("")
async def list_sites(context: Context, user: CurrentUser) -> list[str]:
    """Site folders of the day1 repo."""
    return await context.sites.sites()


@sites_router.get("/{site}/mces")
async def list_site_mces(site: Name, context: Context, user: CurrentUser) -> list[str]:
    """MCE folder names under a site."""
    return await context.sites.mce_names(site)


@mces_router.get("")
async def list_mces(
    context: Context,
    user: CurrentUser,
    site: Annotated[str | None, Query(max_length=63)] = None,
) -> list[MceOut]:
    """Every MCE (or one site's), with its default mastertag, hub version and naming."""
    return [MceOut.of(view) for view in await context.sites.mces(site)]


@mces_router.get("/{mce}/infraenvs")
async def list_infraenvs(mce: Name, user: CurrentUser, status: Status) -> list[str]:
    """InfraEnv names on the MCE hub (501 when live status is off)."""
    return await status.infra_envs(mce)
