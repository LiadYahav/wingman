"""A team's operators, for the Operators pages (ADR-0053).

The writes are the authoring routes (``api.v1.authoring``), under
``/addons/{team}/{addon}``: the API keeps calling an operator an add-on.
"""

from __future__ import annotations

from fastapi import APIRouter

from wingman_core.web.auth import CurrentUser
from wingman_day2.api.v1.dependencies import Services
from wingman_day2.api.v1.schemas import OperatorOut, OperatorSummaryOut

router = APIRouter(prefix="/api/day2", tags=["operators"])


@router.get("/teams/{team}/operators")
async def list_operators(team: str, user: CurrentUser, day2: Services) -> list[OperatorSummaryOut]:
    """The team's operators: its catalog plus fleet defaults of charts not in it."""
    return [OperatorSummaryOut.of(s) for s in await day2.operators.summaries(team)]


@router.get("/teams/{team}/operators/{operator}")
async def get_operator(team: str, operator: str, user: CurrentUser, day2: Services) -> OperatorOut:
    """One operator: its files, its OCP-version pins, and per scope its default's destinations."""
    return OperatorOut.of(await day2.operators.detail(team, operator))
