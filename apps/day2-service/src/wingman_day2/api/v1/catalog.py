"""Teams, the chart catalog, chart versions and chart default values; repo lints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from wingman_core.web.auth import CurrentUser
from wingman_day2.api.v1.dependencies import Services
from wingman_day2.api.v1.schemas import (
    CatalogEntryOut,
    FindingOut,
    GitLabInfoOut,
    TeamOut,
    findings,
)

router = APIRouter(prefix="/api/day2", tags=["catalog"])


@router.get("/gitlab-info")
async def gitlab_info(user: CurrentUser, day2: Services) -> GitLabInfoOut:
    """Where the sigs group lives, for links."""
    info = day2.info
    return GitLabInfoOut(
        gitlab_url=info.gitlab_url,
        sigs_group_path=info.sigs_group,
        sigs_group_url=f"{info.gitlab_url}/groups/{info.sigs_group}",
    )


@router.get("/teams")
async def list_teams(user: CurrentUser, day2: Services) -> list[TeamOut]:
    """Every team: each project directly in the sigs group."""
    topology = await day2.topology.load()
    return [TeamOut.of(state.team) for state in topology.teams]


@router.get("/addons")
async def list_addons(
    user: CurrentUser, day2: Services, team: str | None = Query(default=None)
) -> list[CatalogEntryOut]:
    """Every catalog entry (``operators/<chart>/``), optionally one team's."""
    return [CatalogEntryOut.of(e) for e in await day2.catalog.entries(team)]


@router.get("/addons/{team}/{addon}")
async def get_addon(team: str, addon: str, user: CurrentUser, day2: Services) -> CatalogEntryOut:
    """One catalog entry."""
    return CatalogEntryOut.of(await day2.catalog.entry(team, addon))


@router.get("/addons/{team}/{addon}/versions")
async def get_addon_versions(team: str, addon: str, user: CurrentUser, day2: Services) -> list[str]:
    """The chart repo's branches (releases), default branch first."""
    return await day2.catalog.versions(team, addon)


@router.get("/addons/{team}/{addon}/values")
async def get_addon_values(
    team: str,
    addon: str,
    user: CurrentUser,
    day2: Services,
    version: str = Query(default="HEAD", description="A chart repo branch; HEAD = default branch"),
) -> dict[str, Any]:
    """The chart's own ``values.yaml`` at ``version`` (``{}`` when it cannot be read)."""
    return (await day2.catalog.default_values(team, addon, version)).values


@router.get("/lints")
async def lints(
    user: CurrentUser, day2: Services, team: str | None = Query(default=None)
) -> list[FindingOut]:
    """Every check on the team repos: render_chain.py's rules plus Wingman's own."""
    return findings(await day2.lints.report(team))
