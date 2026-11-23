"""``/api/day1/inventory``: Inventory Management (ADR-0057).

Each MCE's available Agents by InfraEnv pool, as server-scan counts them; a
pool's servers for a named install; the add-server runs, herzi's included;
and adding servers through the platform's add-server-to-mce workflow.
Admins only (``AdminUser``), reads too since ADR-0067: herzi fills the
customers' demand, so a viewer never reads the inventory (a ``403``).
The API is ``docs/notes/2026-11-13-inventory-management-api.md``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path

from wingman_core.web.auth import AdminUser
from wingman_day1.api.deps import Inventory
from wingman_day1.api.v1.inventory_schemas import (
    AddServersIn,
    AddServersOut,
    CandidatesOut,
    InventoryOut,
    InventoryRunOut,
    InventoryRunsOut,
)

router = APIRouter(prefix="/api/day1/inventory", tags=["inventory"])

Mce = Annotated[str, Path(min_length=1, max_length=63, description="A day1 MCE folder")]
InfraEnv = Annotated[
    str,
    Path(
        min_length=1,
        max_length=253,
        description="An InfraEnv (a DNS label; the workflow checks the MCE has it)",
    ),
]


@router.get("")
async def inventory(user: AdminUser, service: Inventory) -> InventoryOut:
    """Every MCE's servers and pools, as server-scan counts them, and what is offered here."""
    return InventoryOut.of(await service.overview())


@router.get("/runs")
async def add_server_runs(user: AdminUser, service: Inventory) -> InventoryRunsOut:
    """The newest add-server runs, herzi's and people's; 501 without the orchestrator."""
    return InventoryRunsOut(runs=[InventoryRunOut.of(run) for run in await service.runs()])


@router.get("/mces/{mce}/infra-envs/{infra_env}/candidates")
async def candidates(
    mce: Mce, infra_env: InfraEnv, user: AdminUser, service: Inventory
) -> CandidatesOut:
    """The servers a named install into this pool may pick, and why a server is not offered.

    The free servers the InfraEnv's agentLabels name (``server_prefix``), or every free
    server when they are unknown or name none: the workflow checks the server named.
    """
    return CandidatesOut.of(mce, await service.candidates(mce, infra_env))


@router.post("/mces/{mce}/infra-envs/{infra_env}/add-servers", status_code=202)
async def add_servers(
    mce: Mce, infra_env: InfraEnv, body: AddServersIn, user: AdminUser, service: Inventory
) -> AddServersOut:
    """Start add-server-to-mce: one run per server. Never retried; sent again, it installs more.

    Needs no live status: whether the InfraEnv is on the MCE is the workflow's first check.
    ``allow_unhealthy`` waives the workflow's health checks for the named servers only (422
    on a pool draw).
    """
    result = await service.add_servers(
        mce,
        infra_env,
        count=body.count,
        server_names=body.server_names or (),
        user=user,
        allow_unhealthy=body.allow_unhealthy,
    )
    return AddServersOut.of(result)
