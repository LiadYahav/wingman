"""``/api/day1/clusters/{name}/upgrade*`` and ``/api/day1/upgrades``: upgrades through the workflow.

ADR-0055, docs/notes/2026-11-13-upgrade-cluster-workflow-api.md. Behind
``DAY1_UPGRADES``: off, every route answers 501. ``{name}`` is the cluster
file's stem, which is the workflow's ``cluster``. Reading a run, or the
fleet's runs, needs a session; the targets, a start and every decision need
an admin, who is the ``by`` the workflow records. A viewer's run has no
agent proposals (ADR-0038, amended 2026-11-23).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from wingman_core.web.auth import AdminUser, CurrentUser
from wingman_day1.api.deps import Context, Upgrades
from wingman_day1.api.v1.upgrade_schemas import (
    FleetUpgradeOut,
    FleetUpgradesOut,
    StartUpgradeIn,
    UpgradeDecisionIn,
    UpgradeDecisionOut,
    UpgradeRunOut,
    UpgradeTargetsOut,
)
from wingman_day1.api.v1.visible import cluster_ref
from wingman_day1.domain.upgrades import UpgradeDecision
from wingman_day1.domain.visibility import sees_cluster

router = APIRouter(prefix="/api/day1", tags=["upgrades"])

Site = Annotated[str | None, Query(max_length=63, description="Site folder")]
Mce = Annotated[str | None, Query(max_length=63, description="MCE folder")]
ActionId = Annotated[
    str,
    Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$", description="The proposal"),
]


@router.get("/upgrades")
async def fleet_upgrades(user: CurrentUser, upgrades: Upgrades) -> FleetUpgradesOut:
    """Every cluster's newest upgrade run, open ones first, from the orchestrator's run list.

    A viewer's list has no KV cluster's run (ADR-0067).
    """
    rows = [
        row
        for row in await upgrades.fleet()
        if sees_cluster(user, row.row.cluster, mce=row.ref.mce if row.ref else "")
    ]
    return FleetUpgradesOut(runs=[FleetUpgradeOut.of(row) for row in rows])


@router.get("/clusters/{name}/upgrade-targets")
async def upgrade_targets(
    name: str,
    context: Context,
    upgrades: Upgrades,
    user: AdminUser,
    site: Site = None,
    mce: Mce = None,
) -> UpgradeTargetsOut:
    """What the workflow offers to upgrade the cluster to; it may take up to a minute."""
    ref = await cluster_ref(context, user, name, site, mce)
    return UpgradeTargetsOut.of(await upgrades.targets(ref))


@router.post("/clusters/{name}/upgrade", status_code=202)
async def start_upgrade(
    name: str,
    body: StartUpgradeIn,
    context: Context,
    upgrades: Upgrades,
    user: AdminUser,
    site: Site = None,
    mce: Mce = None,
) -> UpgradeRunOut:
    """Start the upgrade-cluster workflow: it plans, checks, and waits for approval."""
    ref = await cluster_ref(context, user, name, site, mce)
    return UpgradeRunOut.of(await upgrades.start(ref, body.choice(), user=user))


@router.get("/clusters/{name}/upgrade-run")
async def upgrade_run(
    name: str,
    context: Context,
    upgrades: Upgrades,
    user: CurrentUser,
    site: Site = None,
    mce: Mce = None,
) -> UpgradeRunOut:
    """The cluster's newest upgrade run, read by its id (404 when it never had one).

    For a viewer, ``pending_actions`` is empty: a proposal may act on one of the cluster's nodes.
    """
    run = await upgrades.run(await cluster_ref(context, user, name, site, mce))
    return UpgradeRunOut.of(run if user.is_admin else run.without_proposals())


@router.post("/clusters/{name}/upgrade-run/actions/{action_id}/{verdict}")
async def decide_action(
    name: str,
    action_id: ActionId,
    verdict: Annotated[str, Path(pattern="^(approve|reject)$")],
    context: Context,
    upgrades: Upgrades,
    user: AdminUser,
    site: Site = None,
    mce: Mce = None,
) -> UpgradeDecisionOut:
    """Approve or reject one of the upgrade agent's proposals."""
    ref = await cluster_ref(context, user, name, site, mce)
    decided = await upgrades.decide_action(ref, action_id, approve=verdict == "approve", user=user)
    return UpgradeDecisionOut.of(decided)


@router.post("/clusters/{name}/upgrade-run/{decision}")
async def decide(
    name: str,
    decision: UpgradeDecision,
    context: Context,
    upgrades: Upgrades,
    user: AdminUser,
    body: UpgradeDecisionIn | None = None,
    site: Site = None,
    mce: Mce = None,
) -> UpgradeDecisionOut:
    """Send one decision; the run's validator judges it, and a refusal is a 409 in its words."""
    ref = await cluster_ref(context, user, name, site, mce)
    sent = body or UpgradeDecisionIn()
    decided = await upgrades.decide(
        ref, decision, user=user, reason=sent.reason, nodepool=sent.nodepool
    )
    return UpgradeDecisionOut.of(decided)
