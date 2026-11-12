"""Which destinations a fleet default reaches and what one of them gets (ADR-0053)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial

import pytest
import yaml

from wingman_core.domain.git import ChangeKind
from wingman_core.domain.mr_conventions import Verb, parse_mr_title
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day2.application.authoring import AuthoringResult, Effect
from wingman_day2.application.services import Day2Services
from wingman_day2.domain.clusters import DefaultsScope
from wingman_day2.domain.errors import (
    ChangeRefusedError,
    ChartNotInstalledError,
    PlanChangedError,
    TeamReadOnlyError,
)
from wingman_day2.domain.findings import Rule
from wingman_day2.domain.platform import AppSource, TeamPlan

MCES = DefaultsScope.MCES
PREP = "mce:site1:prep:ocp4-prep-mce-site1-a"
PROD = "mce:site1:prod:ocp4-prod-mce-site1-a"
EXCLUSIONS = "defaults/mces/exclusions.yaml"
PROD_IN_CLUSTER = "sites/site1/prod/mces/ocp4-prod-mce-site1-a/in-cluster"


async def confirmed(write: Callable[..., Awaitable[AuthoringResult]]) -> AuthoringResult:
    preview = await write(dry_run=True)
    return await write(
        confirm_changes=preview.plan.needs_confirmation, expected_digest=preview.plan.digest
    )


async def main_files(gitlab: InMemoryGitLab, branch: str = "main") -> dict[str, str]:
    project = await gitlab.get_project("sigs/redbull")
    return gitlab.snapshot(project.id, branch)


async def merge(services: Day2Services, result: AuthoringResult, approver: User) -> None:
    mr = result.merge_request
    assert mr is not None
    await services.approvals.approve(result.plan.team, mr.ref.iid, sha=mr.sha, approver=approver)


def apps_of(plan: TeamPlan, chart: str) -> dict[str, AppSource]:
    return {a.ref.id: a.source for a in plan.apps if a.chart == chart}


# ── exclusions ──────────────────────────────────────────────────────────────


async def test_excluding_an_mce_orphans_its_app_and_must_be_confirmed(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User, bob_user: User
) -> None:
    before = await main_files(gitlab)
    excl = partial(
        services.fleet_targets.set_exclusions,
        "redbull",
        "dhcp-api-token",
        MCES,
        [PREP, PROD],
        jane_user,
    )
    plan = (await excl(dry_run=True)).plan
    (impact,) = plan.impact
    assert (impact.ref.id, impact.effect, impact.orphaned) == (PROD, Effect.REMOVED, True)
    assert impact.app_name == "redbull-in-cluster-dhcp-api-token-deploy"
    assert plan.needs_confirmation == [PROD] and plan.reach == []
    assert [(c.kind, str(c.path)) for c in plan.changes] == [(ChangeKind.UPDATE, EXCLUSIONS)]
    # One line more; the 40 comment lines and everything else byte for byte.
    assert plan.changes[0].content == before[EXCLUSIONS].replace(
        "    - ocp4-prep-mce-site1-a\n",
        "    - ocp4-prep-mce-site1-a\n    - ocp4-prod-mce-site1-a\n",
    )
    assert "orphans the workload" in " ".join(plan.notes)
    assert plan.title == (
        "[Wingman/Day2] Exclude addon redbull/dhcp-api-token from ocp4-prod-mce-site1-a "
        "(fleet default on every MCE)"
    )
    with pytest.raises(ChangeRefusedError) as raised:
        await excl()
    assert raised.value.details["rule"] == "confirm-changes"
    result = await confirmed(excl)
    assert result.merge_request is not None
    title = parse_mr_title(result.merge_request.title)
    assert title is not None and title.verb is Verb.EXCLUDE
    assert set(result.merge_request.labels) == {"wingman", "day2", "set-exclusions"}
    assert "**Applications this deletes." in result.merge_request.description
    await merge(services, result, bob_user)
    after = (await services.topology.load()).team("redbull")
    assert "dhcp-api-token" not in {a.chart for a in after.plan.apps}
    assert after.findings == ()


async def test_including_an_mce_brings_its_app_back_without_confirmation(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User, bob_user: User
) -> None:
    before = await main_files(gitlab)
    result = await services.fleet_targets.set_exclusions(
        "redbull", "dhcp-api-token", MCES, [], jane_user
    )
    plan = result.plan
    assert [(i.ref.id, i.effect) for i in plan.impact] == [(PREP, Effect.ADDED)]
    assert plan.needs_confirmation == []
    assert result.merge_request is not None
    text = (await main_files(gitlab, result.merge_request.source_branch))[EXCLUSIONS]
    assert text.endswith("exclusions: {}\n")
    comments = [x for x in before[EXCLUSIONS].splitlines() if x.lstrip().startswith("#")]
    assert [x for x in text.splitlines() if x.lstrip().startswith("#")] == comments
    assert plan.title.startswith("[Wingman/Day2] Include addon redbull/dhcp-api-token on ")
    await merge(services, result, bob_user)
    after = (await services.topology.load()).team("redbull")
    assert apps_of(after.plan, "dhcp-api-token") == {
        PREP: AppSource.FLEET_DEFAULT,
        PROD: AppSource.FLEET_DEFAULT,
    }


async def test_a_chart_without_an_entry_gets_one_after_the_last(
    services: Day2Services, jane_user: User
) -> None:
    result = await confirmed(
        partial(
            services.fleet_targets.set_exclusions,
            "redbull",
            "example-chart",
            MCES,
            [PREP],
            jane_user,
        )
    )
    content = result.plan.changes[0].content or ""
    assert content.endswith(
        "  dhcp-api-token:\n    - ocp4-prep-mce-site1-a\n  example-chart:\n"
        "    - ocp4-prep-mce-site1-a\n"
    )


async def test_exclusion_refusals(services: Day2Services, jane_user: User) -> None:
    targets = services.fleet_targets
    cases = [
        (
            targets.set_exclusions("redbull", "example-chart", DefaultsScope.HUB, [], jane_user),
            "hub-override",
        ),
        (
            targets.set_exclusions("redbull", "dhcp-api-token", MCES, ["hub"], jane_user),
            "destination-unknown",
        ),
        (targets.set_exclusions("redbull", "dhcp-api-token", MCES, [PREP], jane_user), "no-change"),
    ]
    for write, rule in cases:
        with pytest.raises(ChangeRefusedError) as raised:
            await write
        assert raised.value.details["rule"] == rule
    with pytest.raises(ChartNotInstalledError):
        await targets.set_exclusions("redbull", "bmhgen", MCES, [], jane_user)
    with pytest.raises(TeamReadOnlyError):
        await targets.set_exclusions("orca", "metrics", DefaultsScope.UPI, [], jane_user)


async def test_a_preview_the_repo_moved_away_from_is_refused(
    services: Day2Services, jane_user: User, bob_user: User
) -> None:
    excl = partial(
        services.fleet_targets.set_exclusions,
        "redbull",
        "dhcp-api-token",
        MCES,
        [PREP, PROD],
        jane_user,
    )
    preview = (await excl(dry_run=True)).plan
    # A change that leaves this plan as it was does not refuse it: the digest is the same.
    unrelated = await confirmed(
        partial(
            services.fleet_targets.set_destination_values,
            "redbull",
            "dhcp-api-token",
            MCES,
            PROD,
            {"note": "x"},
            jane_user,
        )
    )
    await merge(services, unrelated, bob_user)
    assert (await excl(dry_run=True)).plan.digest == preview.digest
    # Someone else's change to the same file lands between the preview and the submit.
    other = await confirmed(
        partial(
            services.fleet_targets.set_exclusions,
            "redbull",
            "example-chart",
            MCES,
            [PREP],
            jane_user,
        )
    )
    await merge(services, other, bob_user)
    with pytest.raises(PlanChangedError) as raised:
        await excl(confirm_changes=preview.needs_confirmation, expected_digest=preview.digest)
    assert raised.value.details["rule"] == "plan-changed"
    assert raised.value.details["digest"] != preview.digest


# ── values for one destination ──────────────────────────────────────────────


async def test_a_destination_override_changes_that_destination_only(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    write = partial(
        services.fleet_targets.set_destination_values,
        "redbull",
        "example-chart",
        MCES,
        PROD,
        {"replicas": 3},
        jane_user,
    )
    plan = (await write(dry_run=True)).plan
    path = "defaults/mces/example-chart/values-ocp4-prod-mce-site1-a.yaml"
    assert [(c.kind, str(c.path)) for c in plan.changes] == [(ChangeKind.CREATE, path)]
    (impact,) = plan.impact
    assert impact.ref.id == PROD and impact.effect is Effect.CHANGED
    assert [(c.stack, c.key, c.before, c.after) for c in impact.changes] == [
        ("values", "replicas", None, 3)
    ]
    assert plan.title == (
        "[Wingman/Day2] Override addon redbull/example-chart values on ocp4-prod-mce-site1-a "
        "(fleet default on every MCE)"
    )
    result = await confirmed(write)
    assert result.merge_request is not None
    branch = await main_files(gitlab, result.merge_request.source_branch)
    assert yaml.safe_load(branch[path]) == {"replicas": 3}


async def test_removing_a_destination_override_deletes_its_file_guarded(
    services: Day2Services, jane_user: User
) -> None:
    detail = await services.operators.detail("redbull", "example-chart")
    mces = next(s for s in detail.scopes if s.scope is MCES)
    prep = next(d for d in mces.destinations if d.ref.id == PREP)
    assert prep.override is not None and prep.override.file is not None
    result = await confirmed(
        partial(
            services.fleet_targets.set_destination_values,
            "redbull",
            "example-chart",
            MCES,
            PREP,
            None,
            jane_user,
            last_commit_id=prep.override.file.last_commit_id,
        )
    )
    (change,) = result.plan.changes
    assert change.kind is ChangeKind.DELETE and change.last_commit_id
    assert result.plan.title.endswith(
        "values on ocp4-prep-mce-site1-a: back to the fleet default (fleet default on every MCE)"
    )


async def test_destination_override_refusals(services: Day2Services, jane_user: User) -> None:
    targets = services.fleet_targets
    with pytest.raises(ChangeRefusedError) as raised:
        await targets.set_destination_values(
            "redbull", "example-chart", DefaultsScope.HUB, "hub", {"a": 1}, jane_user
        )
    assert raised.value.details["rule"] == "hub-override"
    with pytest.raises(ChangeRefusedError) as raised:
        await targets.set_destination_values(
            "redbull", "example-chart", MCES, PROD, None, jane_user
        )
    assert raised.value.details["rule"] == "no-change"


# ── deploy config for one destination ───────────────────────────────────────


async def test_an_own_deploy_config_is_an_exclusion_and_a_folder_in_one_commit(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User, bob_user: User
) -> None:
    before = (await services.topology.load()).team("redbull").plan
    names = {(a.ref.id, a.generator_app) for a in before.apps if a.chart == "example-chart"}
    write = partial(
        services.fleet_targets.set_destination_deploy,
        "redbull",
        "example-chart",
        MCES,
        PROD,
        {"targetRevision": "0.1.0"},
        jane_user,
    )
    plan = (await write(dry_run=True)).plan
    own = f"{PROD_IN_CLUSTER}/example-chart/example-chart.yaml"
    assert [(c.kind, str(c.path)) for c in plan.changes] == [
        (ChangeKind.CREATE, own),
        (ChangeKind.UPDATE, EXCLUSIONS),
    ]
    assert plan.changes[0].content == "targetRevision: 0.1.0\n"
    (impact,) = plan.impact
    assert impact.effect is Effect.CHANGED and impact.ref.id == PROD
    assert [(c.key, c.before, c.after) for c in impact.changes] == [
        ("targetRevision", "main", "0.1.0")
    ]
    assert Rule.EMERGENCY_PIN in {f.rule for f in plan.findings}
    result = await confirmed(write)
    await merge(services, result, bob_user)
    after = (await services.topology.load()).team("redbull")
    # The same wrapper apps: ArgoCD keeps the prod MCE's, now from its own folder.
    assert {(a.ref.id, a.generator_app) for a in after.plan.apps if a.chart == "example-chart"} == (
        names
    )
    assert apps_of(after.plan, "example-chart")[PROD] is AppSource.CLUSTER
    assert after.findings == ()
    detail = await services.operators.detail("redbull", "example-chart")
    mces = next(s for s in detail.scopes if s.scope is MCES)
    state = {d.ref.id: str(d.state) for d in mces.destinations}
    assert state == {PREP: "default", PROD: "own-deploy"}
    # Including it while it has its own deploy config would duplicate the app.
    with pytest.raises(ChangeRefusedError) as raised:
        await services.fleet_targets.set_exclusions("redbull", "example-chart", MCES, [], jane_user)
    assert raised.value.details["rule"] == "own-deploy"
    # Taking it back moves the folder into the default and drops the entry, in one commit.
    back = await confirmed(
        partial(
            services.fleet_targets.set_destination_deploy,
            "redbull",
            "example-chart",
            MCES,
            PROD,
            None,
            jane_user,
        )
    )
    assert sorted((c.kind, str(c.path)) for c in back.plan.changes) == sorted(
        [(ChangeKind.DELETE, own), (ChangeKind.UPDATE, EXCLUSIONS)]
    )
    await merge(services, back, bob_user)
    final = (await services.topology.load()).team("redbull")
    assert apps_of(final.plan, "example-chart")[PROD] is AppSource.FLEET_DEFAULT
    assert {(a.ref.id, a.generator_app) for a in final.plan.apps if a.chart == "example-chart"} == (
        names
    )
