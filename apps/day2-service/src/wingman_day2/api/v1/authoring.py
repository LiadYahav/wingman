"""Add-on authoring: a new one, its team default, fleet defaults, and installs on MCEs.

ADR-0043 and ADR-0053. Every write takes ``?dry_run=true``: it runs every
check, opens nothing, and answers 200 with the plan (its ``impact`` and
``digest``); without it, 201 (create, make default) or 200 (edits) with the
opened MR. What the plan deletes or changes must be confirmed by id in
``confirm_changes`` with the preview's ``digest`` as ``expected_digest``; a
repo that moved since the preview answers 409 ``plan-changed``. A team that
has not given Wingman write access to its project gets 403
``TEAM_READ_ONLY`` before anything else is checked.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from wingman_core.web.auth import AdminUser, CurrentUser
from wingman_day2.api.v1.dependencies import Services
from wingman_day2.api.v1.schemas import (
    AddonTemplateOut,
    AuthoringChangeOut,
    AuthoringPlanOut,
    CreateAddonBody,
    DestinationValuesBody,
    FleetDefaultOut,
    MakeDefaultBody,
    MceInstallsBody,
    MceInstallsOut,
    UpdateFleetDefaultBody,
    UpdateTeamDefaultBody,
)
from wingman_day2.application.authoring import UNSET, AuthoringResult
from wingman_day2.domain.clusters import DefaultsScope

router = APIRouter(prefix="/api/day2", tags=["authoring"])

DryRun = Query(default=False, description="Plan and check only; open nothing (200).")


def _answer(
    result: AuthoringResult, response: Response, *, created: bool
) -> AuthoringPlanOut | AuthoringChangeOut:
    if result.merge_request is None:
        response.status_code = status.HTTP_200_OK
        return AuthoringPlanOut.of(result.plan)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return AuthoringChangeOut.of_result(result)


@router.get("/teams/{team}/addon-template")
async def addon_template(team: str, user: CurrentUser, day2: Services) -> AddonTemplateOut:
    """What a new add-on of the team starts from: its usual sync options and chart repos."""
    return AddonTemplateOut.of(await day2.authoring.template(team))


@router.get("/fleet-defaults")
async def list_fleet_defaults(
    user: CurrentUser, day2: Services, team: str | None = Query(default=None)
) -> list[FleetDefaultOut]:
    """Every ``defaults/<scope>/<chart>/``, with what it reaches and its sync options."""
    return [FleetDefaultOut.of(d) for d in await day2.authoring.fleet_defaults(team)]


@router.post("/addons/{team}", status_code=status.HTTP_201_CREATED)
async def create_addon(
    team: str,
    body: CreateAddonBody,
    user: AdminUser,
    day2: Services,
    response: Response,
    dry_run: bool = DryRun,
) -> AuthoringPlanOut | AuthoringChangeOut:
    """Open an MR adding ``operators/<name>/`` (and, with ``default_scope``, a fleet default)."""
    result = await day2.authoring.create(
        body.spec(team),
        user,
        dry_run=dry_run,
        message=body.message,
        expected_digest=body.expected_digest,
    )
    return _answer(result, response, created=True)


@router.put("/addons/{team}/{addon}")
async def update_team_default(
    team: str,
    addon: str,
    body: UpdateTeamDefaultBody,
    user: AdminUser,
    day2: Services,
    response: Response,
    dry_run: bool = DryRun,
) -> AuthoringPlanOut | AuthoringChangeOut:
    """Open an MR editing the add-on's team default (deploy config edited in place, values)."""
    result = await day2.authoring.update_team_default(
        team,
        addon,
        body.edit(),
        user,
        dry_run=dry_run,
        message=body.message,
        confirm_changes=body.confirm_changes,
        expected_digest=body.expected_digest,
    )
    return _answer(result, response, created=False)


@router.post("/addons/{team}/{addon}/defaults/{scope}", status_code=status.HTTP_201_CREATED)
async def make_default(
    team: str,
    addon: str,
    scope: DefaultsScope,
    body: MakeDefaultBody,
    user: AdminUser,
    day2: Services,
    response: Response,
    dry_run: bool = DryRun,
) -> AuthoringPlanOut | AuthoringChangeOut:
    """Open an MR making the add-on a fleet default; clusters that have it move into it."""
    result = await day2.authoring.make_default(
        team,
        addon,
        scope,
        user,
        values=body.values,
        sync=body.sync.settings() if body.sync is not None else None,
        confirm_changes=body.confirm_changes,
        dry_run=dry_run,
        message=body.message,
        expected_digest=body.expected_digest,
    )
    return _answer(result, response, created=True)


@router.put("/addons/{team}/{addon}/defaults/{scope}")
async def update_fleet_default(
    team: str,
    addon: str,
    scope: DefaultsScope,
    body: UpdateFleetDefaultBody,
    user: AdminUser,
    day2: Services,
    response: Response,
    dry_run: bool = DryRun,
) -> AuthoringPlanOut | AuthoringChangeOut:
    """Open an MR editing a fleet default's values and sync options."""
    if "sync" not in body.model_fields_set:
        sync = UNSET
    else:
        sync = body.sync.settings() if body.sync is not None else None
    result = await day2.authoring.update_fleet_default(
        team,
        addon,
        scope,
        user,
        values=body.values,
        sync=sync,
        last_commit_id=body.last_commit_id,
        dry_run=dry_run,
        message=body.message,
        confirm_changes=body.confirm_changes,
        expected_digest=body.expected_digest,
    )
    return _answer(result, response, created=False)


@router.put("/addons/{team}/{addon}/defaults/{scope}/destinations/{cluster}/values")
async def set_destination_values(
    team: str,
    addon: str,
    scope: DefaultsScope,
    cluster: str,
    body: DestinationValuesBody,
    user: AdminUser,
    day2: Services,
    response: Response,
    dry_run: bool = DryRun,
) -> AuthoringPlanOut | AuthoringChangeOut:
    """Open an MR setting one destination's ``values-<name>.yaml`` (null or {} deletes it)."""
    result = await day2.fleet_targets.set_destination_values(
        team,
        addon,
        scope,
        cluster,
        body.values,
        user,
        last_commit_id=body.last_commit_id,
        confirm_changes=body.confirm_changes,
        expected_digest=body.expected_digest,
        dry_run=dry_run,
        message=body.message,
    )
    return _answer(result, response, created=False)


@router.put("/addons/{team}/{addon}/defaults/{scope}/envs/{env}/values")
async def set_env_values(
    team: str,
    addon: str,
    scope: DefaultsScope,
    env: str,
    body: DestinationValuesBody,
    user: AdminUser,
    day2: Services,
    response: Response,
    dry_run: bool = DryRun,
) -> AuthoringPlanOut | AuthoringChangeOut:
    """Open an MR setting one env's ``values-<env>.yaml`` of a fleet default ({} deletes it)."""
    result = await day2.fleet_targets.set_env_values(
        team,
        addon,
        scope,
        env,
        body.values,
        user,
        last_commit_id=body.last_commit_id,
        confirm_changes=body.confirm_changes,
        expected_digest=body.expected_digest,
        dry_run=dry_run,
        message=body.message,
    )
    return _answer(result, response, created=False)


@router.post("/addons/{team}/{addon}/mce-installs")
async def install_on_mces(
    team: str,
    addon: str,
    body: MceInstallsBody,
    user: AdminUser,
    day2: Services,
    response: Response,
    dry_run: bool = DryRun,
) -> MceInstallsOut:
    """Deploy the add-on on specific MCEs: one MR per MCE, each in its own folder.

    200 with each MCE planned or refused (dry run), or opened, refused or
    failed; 201 when at least one MR opened.
    """
    result = await day2.changes.install_on_mces(
        team,
        addon,
        body.clusters,
        user,
        values=body.values,
        dry_run=dry_run,
        message=body.message,
    )
    if any(i.result is not None for i in result.installs):
        response.status_code = status.HTTP_201_CREATED
    return MceInstallsOut.of(result)
