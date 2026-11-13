"""One destination's values of a fleet default (ADR-0053; no exclusions since its amendment)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial

import pytest
import yaml

from wingman_core.domain.git import ChangeKind, FileChange, RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day2.application.authoring import AuthoringResult, Effect
from wingman_day2.application.services import Day2Services
from wingman_day2.domain.clusters import DefaultsScope
from wingman_day2.domain.errors import (
    ChangeRefusedError,
    ChartNotInstalledError,
    PlanChangedError,
)

MCES = DefaultsScope.MCES
HOSTED = DefaultsScope.HOSTED_CLUSTERS
PREP = "mce:site1:prep:ocp4-prep-mce-site1-a"
PROD = "mce:site1:prod:ocp4-prod-mce-site1-a"


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


async def test_the_digest_takes_values_yaml_allows_and_json_cannot_sort(
    services: Day2Services, jane_user: User
) -> None:
    write = partial(
        services.fleet_targets.set_destination_values,
        "redbull",
        "example-chart",
        MCES,
        PROD,
        {"items": [{1: "one", "b": 2}]},
        jane_user,
    )
    first, again = (await write(dry_run=True)).plan, (await write(dry_run=True)).plan
    assert len(first.digest) == 64 and first.digest == again.digest


async def test_destination_override_refusals(services: Day2Services, jane_user: User) -> None:
    targets = services.fleet_targets
    with pytest.raises(ChangeRefusedError) as raised:
        await targets.set_destination_values(
            "redbull", "example-chart", DefaultsScope.HUB, "hub", {"a": 1}, jane_user
        )
    assert raised.value.details["rule"] == "override-scope"
    with pytest.raises(ChangeRefusedError) as raised:
        await targets.set_destination_values(
            "redbull", "example-chart", MCES, PROD, None, jane_user
        )
    assert raised.value.details["rule"] == "no-change"


# ── deploy config for one destination ───────────────────────────────────────


async def test_a_preview_the_repo_moved_away_from_is_refused(
    services: Day2Services, jane_user: User, bob_user: User
) -> None:
    write = partial(
        services.fleet_targets.set_destination_values,
        "redbull",
        "dhcp-api-token",
        MCES,
        PROD,
        {"note": "mine"},
        jane_user,
    )
    preview = (await write(dry_run=True)).plan
    # A change that leaves this plan as it was does not refuse it: the digest is the same.
    unrelated = await confirmed(
        partial(
            services.fleet_targets.set_destination_values,
            "redbull",
            "example-chart",
            MCES,
            PROD,
            {"replicas": 2},
            jane_user,
        )
    )
    await merge(services, unrelated, bob_user)
    assert (await write(dry_run=True)).plan.digest == preview.digest
    # Someone else's values for the same MCE land between the preview and the submit.
    other = await confirmed(
        partial(
            services.fleet_targets.set_destination_values,
            "redbull",
            "dhcp-api-token",
            MCES,
            PROD,
            {"note": "theirs"},
            jane_user,
        )
    )
    await merge(services, other, bob_user)
    with pytest.raises(PlanChangedError) as raised:
        await write(confirm_changes=preview.needs_confirmation, expected_digest=preview.digest)
    assert raised.value.details["rule"] == "plan-changed"


async def test_the_hub_has_no_values_of_its_own_per_env_or_destination(
    services: Day2Services, jane_user: User
) -> None:
    targets = services.fleet_targets
    for write in [
        targets.set_destination_values(
            "redbull", "example-chart", DefaultsScope.HUB, "hub", {"a": 1}, jane_user
        ),
        targets.set_env_values(
            "redbull", "example-chart", DefaultsScope.HUB, "prod", {"a": 1}, jane_user
        ),
    ]:
        with pytest.raises(ChangeRefusedError) as raised:
            await write
        assert raised.value.details["rule"] == "override-scope"


async def test_a_hosted_cluster_gets_values_of_its_own_like_an_mce(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    # The hosted-cluster defaults mirror the MCE ones (the platform's own README).
    project = await gitlab.get_project("sigs/redbull")
    await gitlab.commit(
        project.id,
        branch="main",
        message="by hand",
        changes=[
            FileChange.create(RepoPath("defaults/hosted-clusters/kyverno/values.yaml"), "{}\n")
        ],
    )
    herzi = "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1"
    plan = (
        await services.fleet_targets.set_destination_values(
            "redbull", "kyverno", HOSTED, herzi, {"replicas": 2}, jane_user, dry_run=True
        )
    ).plan
    assert [str(c.path) for c in plan.changes] == [
        "defaults/hosted-clusters/kyverno/values-ocp4-prod-herzi-site1.yaml"
    ]
    assert [i.ref.id for i in plan.impact] == [herzi]


async def test_an_env_override_changes_that_envs_destinations_only(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    write = partial(
        services.fleet_targets.set_env_values,
        "redbull",
        "example-chart",
        MCES,
        "prep",
        {"replicas": 4},
        jane_user,
    )
    plan = (await write(dry_run=True)).plan
    assert [(c.kind, str(c.path)) for c in plan.changes] == [
        (ChangeKind.CREATE, "defaults/mces/example-chart/values-prep.yaml")
    ]
    assert [(i.ref.id, i.effect) for i in plan.impact] == [(PREP, Effect.CHANGED)]
    assert [r.id for r in plan.reach] == [PREP]
    assert plan.title == (
        "[Wingman/Day2] Override addon redbull/example-chart values for prep "
        "(fleet default on every MCE)"
    )
    result = await confirmed(write)
    assert result.merge_request is not None
    branch = await main_files(gitlab, result.merge_request.source_branch)
    assert yaml.safe_load(branch["defaults/mces/example-chart/values-prep.yaml"]) == {"replicas": 4}


async def test_env_override_refusals(services: Day2Services, jane_user: User) -> None:
    targets = services.fleet_targets
    with pytest.raises(ChangeRefusedError) as raised:
        await targets.set_env_values(
            "redbull", "example-chart", MCES, "staging", {"a": 1}, jane_user
        )
    assert raised.value.details["rule"] == "env-unknown"
    with pytest.raises(ChangeRefusedError) as raised:
        await targets.set_env_values("redbull", "example-chart", MCES, "prod", None, jane_user)
    assert raised.value.details["rule"] == "no-change"
    with pytest.raises(ChartNotInstalledError):
        await targets.set_env_values("redbull", "bmhgen", MCES, "prod", {"a": 1}, jane_user)


async def test_wingman_offers_no_exclusion_or_own_deploy_write(services: Day2Services) -> None:
    # ADR-0053's amendment: an add-on wanted on some MCEs is installed on them instead.
    assert not hasattr(services.fleet_targets, "set_exclusions")
    assert not hasattr(services.fleet_targets, "set_destination_deploy")
