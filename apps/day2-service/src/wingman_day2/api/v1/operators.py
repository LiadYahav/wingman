"""A team's add-ons with their defaults and destinations, for the Addons pages (ADR-0053).

An add-on is a chart in a team's catalog (``operators/<chart>/``, the folder's
name in the team repo) and the fleet defaults built from it. The writes are
the authoring routes (``api.v1.authoring``), under ``/addons/{team}/{addon}``.

3.12.0 served these reads as ``/teams/{team}/operators[/{operator}]``; those
paths stay, as deprecated aliases of the ``/teams/{team}/addons`` ones
(ADR-0053's 2026-11-12 amendment: one place, called add-ons).
"""

from __future__ import annotations

from fastapi import APIRouter

from wingman_core.web.auth import CurrentUser
from wingman_day2.api.v1.dependencies import Services
from wingman_day2.api.v1.operators_schemas import OperatorOut, OperatorSummaryOut

router = APIRouter(prefix="/api/day2", tags=["addons"])


@router.get("/teams/{team}/addons")
async def list_team_addons(
    team: str, user: CurrentUser, day2: Services
) -> list[OperatorSummaryOut]:
    """The team's add-ons: its catalog plus fleet defaults of charts not in it."""
    return [OperatorSummaryOut.of(s) for s in await day2.operators.summaries(team)]


@router.get("/teams/{team}/addons/{addon}")
async def get_team_addon(team: str, addon: str, user: CurrentUser, day2: Services) -> OperatorOut:
    """One add-on: its files, its OCP-version pins, and per scope its default's destinations."""
    return OperatorOut.of(await day2.operators.detail(team, addon))


@router.get("/teams/{team}/operators", deprecated=True)
async def list_operators(team: str, user: CurrentUser, day2: Services) -> list[OperatorSummaryOut]:
    """3.12.0's path of ``GET /teams/{team}/addons``; kept so older clients keep working."""
    return await list_team_addons(team, user, day2)


@router.get("/teams/{team}/operators/{operator}", deprecated=True)
async def get_operator(team: str, operator: str, user: CurrentUser, day2: Services) -> OperatorOut:
    """3.12.0's path of ``GET /teams/{team}/addons/{addon}``; kept so older clients keep working."""
    return await get_team_addon(team, operator, user, day2)
