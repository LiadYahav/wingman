"""``/api/day1/clusters/{name}/scale*``: a cluster's NodePools scaled through update-nodepool.

ADR-0062, docs/notes/2026-11-16-scale-nodepools-api.md. Behind
``DAY1_SCALE_NODEPOOLS``: off, every route answers 501. ``{name}`` is the
cluster file's stem, which is the workflow's ``cluster``. Reading what can
be scaled, and the run, needs a session; a start needs an admin. A viewer's
run names no server, Machine or node (ADR-0038, amended 2026-11-23).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from wingman_core.web.auth import AdminUser, CurrentUser
from wingman_day1.api.deps import Context, Scale
from wingman_day1.api.v1.scale_schemas import ScaleIn, ScaleOptionsOut, ScaleRunOut
from wingman_day1.domain.paths import ClusterRef

router = APIRouter(prefix="/api/day1/clusters", tags=["scale"])

Site = Annotated[str | None, Query(max_length=63, description="Site folder")]
Mce = Annotated[str | None, Query(max_length=63, description="MCE folder")]


async def _ref(context: Context, name: str, site: str | None, mce: str | None) -> ClusterRef:
    return await context.clusters.locate(name, site=site, mce=mce)


@router.get("/{name}/scale")
async def scale_options(
    name: str, context: Context, scale: Scale, user: CurrentUser, site: Site = None, mce: Mce = None
) -> ScaleOptionsOut:
    """The cluster file's NodePools, each named by the chart's rule, and the flavor's locks."""
    return ScaleOptionsOut.of(await scale.options(await _ref(context, name, site, mce)))


@router.post("/{name}/scale", status_code=202)
async def start_scale(
    name: str,
    body: ScaleIn,
    context: Context,
    scale: Scale,
    user: AdminUser,
    site: Site = None,
    mce: Mce = None,
) -> ScaleRunOut:
    """Start update-nodepool: it commits the replicas to day1 main and syncs Argo CD itself."""
    ref = await _ref(context, name, site, mce)
    return ScaleRunOut.of(await scale.start(ref, body.target(), user=user))


@router.get("/{name}/scale-run")
async def scale_run(
    name: str, context: Context, scale: Scale, user: CurrentUser, site: Site = None, mce: Mce = None
) -> ScaleRunOut:
    """The cluster's update-nodepool run, read by its id (404 when it never had one).

    For a viewer, ``result.chosen`` and ``result.deleting`` are empty: they name servers.
    """
    run = await scale.run(await _ref(context, name, site, mce))
    return ScaleRunOut.of(run if user.is_admin else run.without_servers())
