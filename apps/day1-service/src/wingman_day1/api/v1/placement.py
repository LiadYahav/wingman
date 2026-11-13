"""``/api/day1/placement``: where a new hosted cluster goes, and why (ADR-0050).

Any signed-in user may ask; creating still needs an admin, and create checks
the chosen MCE against the same rule. With live status off it still answers,
from the day1 repo and server-scan, with the free pods and servers
``not_checked`` (ADR-0050's amendment).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from wingman_core.web.auth import CurrentUser
from wingman_day1.api.deps import Placements
from wingman_day1.api.v1.placement_schemas import PlacementOut
from wingman_day1.domain.errors import InvalidInputError
from wingman_day1.domain.names import Env

MAX_NEEDS = 64
"""More nodepools than any cluster has: a longer query is refused, not read."""

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
    need: Annotated[
        list[str] | None,
        Query(
            max_length=MAX_NEEDS,
            description="A nodepool's node type and replicas, <infra_env>:<replicas>; repeated",
        ),
    ] = None,
) -> PlacementOut:
    """Every candidate MCE at ``site`` for ``env``: its checks, its numbers, and the pick.

    Without ``version`` every version check is unknown and there is no pick;
    ``versions`` says what the candidates host. Without ``owner`` the first
    ranking step (fewest clusters of this owner) is skipped. ``need`` is each
    nodepool's InfraEnv and replicas (an empty ``need=``: none); without any
    ``need``, the flavor's presets.
    """
    return PlacementOut.of(
        await placements.place(
            site=site,
            env=env,
            version=version or None,
            owner=owner or None,
            flavor=flavor or None,
            needs=parse_needs(need) if need is not None else None,
        )
    )


def parse_needs(raw: list[str]) -> list[tuple[str, int]]:
    """``<infra_env>:<replicas>`` each; anything else is a 422 naming it.

    An empty ``need=`` says "no needs": the form names no node type yet, so
    the flavor's presets are not used either.
    """
    needs: list[tuple[str, int]] = []
    problems: list[str] = []
    for item in raw:
        if not item.strip():
            continue
        infra_env, colon, count = item.strip().rpartition(":")
        if not colon or not infra_env or not count.isascii() or not count.isdigit():
            problems.append(f"need: {item!r} is not <infra_env>:<replicas>")
            continue
        needs.append((infra_env, int(count)))
    if problems:
        raise InvalidInputError("the placement's inputs are not acceptable", problems)
    return needs
