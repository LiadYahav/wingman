"""``/api/day1/placement``: where a new hosted cluster goes, and why (ADR-0050).

Any signed-in user may ask; creating still needs an admin, and create checks
the chosen MCE against the same rule. 501 when the MCE hubs cannot be read
(live status off): the form then asks for the MCE as before.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from wingman_core.web.auth import CurrentUser
from wingman_day1.api.deps import Placements
from wingman_day1.api.v1.schemas import PlacementOut
from wingman_day1.domain.names import Env

router = APIRouter(prefix="/api/day1/placement", tags=["placement"])


@router.get("")
async def placement(
    user: CurrentUser,
    placements: Placements,
    site: Annotated[str, Query(min_length=1, max_length=63, description="Site folder")],
    env: Annotated[Env, Query(description="The environment: prod or prep")],
    version: Annotated[
        str | None, Query(max_length=32, description="OpenShift release, 4.N.N")
    ] = None,
    owner: Annotated[
        str | None, Query(max_length=10, description="The owner: the cluster's mador")
    ] = None,
    flavor: Annotated[str | None, Query(max_length=63, description="The flavor's name")] = None,
) -> PlacementOut:
    """Every candidate MCE at ``site`` for ``env``: its checks, its numbers, and the pick.

    Without ``version`` every version check is unknown and there is no pick;
    ``versions`` says what the candidates host. Without ``owner`` the first
    ranking step (fewest clusters of this owner) is skipped.
    """
    return PlacementOut.of(
        await placements.place(
            site=site, env=env, version=version or None, owner=owner or None, flavor=flavor or None
        )
    )
