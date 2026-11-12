"""Regressions from the review of 3.8.0's add-on authoring (ADR-0053)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from functools import partial

import pytest

from wingman_core.domain.errors import RevisionConflictError
from wingman_core.domain.git import ChangeKind, FileChange, RepoPath
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day2.application.authoring import AuthoringResult, Effect, NewAddon, TeamDefaultEdit
from wingman_day2.application.changes import InstallSpec
from wingman_day2.application.services import Day2Services
from wingman_day2.domain.clusters import DefaultsScope
from wingman_day2.domain.errors import ChangeRefusedError
from wingman_day2.domain.platform import AppSource
from wingman_day2.domain.sync_policy import SyncSettings
from wingman_day2.settings import FAKE_GITLAB_URL

HOSTED = DefaultsScope.HOSTED_CLUSTERS
CHART_REPO = f"{FAKE_GITLAB_URL}/helm-charts/example-chart.git"
HERZI = "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1"
HERZI_DIR = "sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1"
HOSTED_EXCLUSIONS = "defaults/hosted-clusters/exclusions.yaml"


async def confirmed(write: Callable[..., Awaitable[AuthoringResult]]) -> AuthoringResult:
    preview = await write(dry_run=True)
    return await write(
        confirm_changes=preview.plan.needs_confirmation, expected_digest=preview.plan.digest
    )


async def commit(gitlab: InMemoryGitLab, *changes: FileChange) -> None:
    project = await gitlab.get_project("sigs/redbull")
    await gitlab.commit(project.id, branch="main", message="by hand", changes=list(changes))


async def merge(services: Day2Services, result: AuthoringResult, approver: User) -> None:
    mr = result.merge_request
    assert mr is not None
    await services.approvals.approve(result.plan.team, mr.ref.iid, sha=mr.sha, approver=approver)


async def test_create_lists_every_cluster_whose_own_folder_it_changes(
    services: Day2Services, jane_user: User, bob_user: User
) -> None:
    # Review finding 1: herzi has podinfo/ in its own folder (repourl only, replicas: 1). The new
    # team layer sits under it, so a create that sets a namespace, auto-sync with prune, and values
    # changes what herzi deploys; 3.8.0 said "nothing is deployed by the catalog itself".
    install = await services.changes.install(
        HERZI,
        InstallSpec("redbull", "podinfo", values={"replicas": 1}, repourl=CHART_REPO),
        jane_user,
    )
    await services.approvals.approve(
        "redbull", install.merge_request.ref.iid, sha=install.merge_request.sha, approver=bob_user
    )
    spec = NewAddon(
        team="redbull",
        chart="podinfo",
        repourl=CHART_REPO,
        sync=SyncSettings(True, True, True, ("CreateNamespace=true",)),
        project_namespace="other-ns",
        values={"resources": {"limits": {"cpu": "1"}}},
    )
    plan = (await services.authoring.create(spec, jane_user, dry_run=True)).plan
    (impact,) = plan.impact
    assert (impact.ref.id, impact.effect) == (HERZI, Effect.CHANGED)
    assert [(c.stack, c.key, c.after) for c in impact.changes] == [
        ("deploy", "projectNamespace", "other-ns"),
        ("deploy", "syncPolicy.automated.prune", True),
        ("deploy", "syncPolicy.automated.selfHeal", True),
        ("deploy", "syncPolicy.syncOptions", ["CreateNamespace=true"]),
        ("values", "resources.limits.cpu", "1"),
    ]
    assert plan.needs_confirmation == [HERZI]
    assert "Nothing is deployed by the catalog itself" not in " ".join(plan.notes)
    with pytest.raises(ChangeRefusedError) as raised:
        await services.authoring.create(spec, jane_user)
    assert raised.value.details["rule"] == "confirm-changes"
    result = await services.authoring.create(
        replace(spec, confirm_changes=(HERZI,)), jane_user, expected_digest=plan.digest
    )
    assert result.merge_request is not None


async def test_a_team_default_edit_lists_what_it_changes_on_every_destination(
    services: Day2Services, jane_user: User
) -> None:
    plan = (
        await services.authoring.update_team_default(
            "redbull", "bmhgen", TeamDefaultEdit(values={"replicas": 3}), jane_user, dry_run=True
        )
    ).plan
    assert {i.ref.id for i in plan.impact} == {
        "mce:site1:prep:ocp4-prep-mce-site1-a",
        "mce:site1:prod:ocp4-prod-mce-site1-a",
    }
    assert all(i.effect is Effect.CHANGED for i in plan.impact)
    assert plan.needs_confirmation == sorted(i.ref.id for i in plan.impact)


async def test_a_stale_exclusion_of_an_adopted_cluster_goes_in_the_same_commit(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User, bob_user: User
) -> None:
    # Review finding 2: an entry for cluster-roles names herzi while cluster-roles is no default
    # (inert, a lint error). Making it a default moves herzi's own folder into the default; with
    # the entry still there, herzi's app would vanish with no confirmation.
    text = (
        "# Hosted clusters that skip a default.\n"
        "exclusions:\n  cluster-roles:\n    - ocp4-prod-herzi-site1\n"
    )
    await commit(gitlab, FileChange.create(RepoPath(HOSTED_EXCLUSIONS), text))
    make = partial(
        services.authoring.make_default, "redbull", "cluster-roles", HOSTED, jane_user, values={}
    )
    plan = (await make(dry_run=True)).plan
    herzi = next(a for a in plan.adopted if a.ref.id == HERZI)
    assert herzi.exclusion_removed and not herzi.changes
    assert [i for i in plan.impact if i.effect is Effect.REMOVED] == []
    assert plan.needs_confirmation == [HERZI]
    exclusions = next(c for c in plan.changes if str(c.path) == HOSTED_EXCLUSIONS)
    assert exclusions.kind is ChangeKind.UPDATE
    assert exclusions.content == "# Hosted clusters that skip a default.\nexclusions: {}\n"
    assert "would delete the app" in " ".join(plan.notes)
    with pytest.raises(ChangeRefusedError) as raised:
        await make()
    assert raised.value.details["rule"] == "confirm-changes"
    result = await confirmed(make)
    await merge(services, result, bob_user)
    after = (await services.topology.load()).team("redbull")
    hosted = {a.ref.id: a.source for a in after.plan.apps if a.chart == "cluster-roles"}
    assert hosted[HERZI] is AppSource.FLEET_DEFAULT and len(hosted) == 5
    assert after.findings == ()


async def test_an_app_that_would_vanish_is_never_opened_unconfirmed(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    # The same, where the entry cannot be removed exactly: refused with the reason.
    text = "exclusions: {cluster-roles: [ocp4-prod-herzi-site1]}\n"
    await commit(gitlab, FileChange.create(RepoPath(HOSTED_EXCLUSIONS), text))
    with pytest.raises(ChangeRefusedError) as raised:
        await services.authoring.make_default(
            "redbull", "cluster-roles", HOSTED, jane_user, values={}, dry_run=True
        )
    assert raised.value.details["rule"] == "exclusions-layout"


async def test_a_null_in_fleet_values_is_a_change_that_deletes_the_chart_default(
    services: Day2Services, jane_user: User
) -> None:
    # Review finding 5: Helm's null deletes the chart's own default on every adopted cluster.
    plan = (
        await services.authoring.make_default(
            "redbull", "cluster-roles", HOSTED, jane_user, values={"rbac": None}, dry_run=True
        )
    ).plan
    changes = {c.key: c for a in plan.adopted for c in a.changes}
    assert changes["rbac"].after is None and changes["rbac"].after_null
    assert len(plan.needs_confirmation) == 4


async def test_a_values_file_deleted_since_the_read_is_a_conflict(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    # Review finding 8: it was silently created again.
    path = RepoPath("operators/bmhgen/values.yaml")
    project = await gitlab.get_project("sigs/redbull")
    read_at = (await gitlab.read_file(project.id, path, ref="main")).last_commit_id
    await commit(gitlab, FileChange.delete(path))
    with pytest.raises(RevisionConflictError):
        await services.authoring.update_team_default(
            "redbull",
            "bmhgen",
            TeamDefaultEdit(values={"replicas": 3}, last_commit_id=read_at),
            jane_user,
            dry_run=True,
        )


async def test_an_empty_ignore_differences_removes_the_key(
    services: Day2Services, jane_user: User
) -> None:
    plan = (
        await services.authoring.update_team_default(
            "redbull",
            "bmhgen",
            TeamDefaultEdit(keys={"ignoreDifferences": [{"kind": "Secret"}]}),
            jane_user,
            dry_run=True,
        )
    ).plan
    assert "ignoreDifferences" in (plan.changes[0].content or "")
    with pytest.raises(ChangeRefusedError) as raised:
        await services.authoring.update_team_default(
            "redbull", "bmhgen", TeamDefaultEdit(keys={"ignoreDifferences": []}), jane_user
        )
    assert raised.value.details["rule"] == "no-change"


async def test_adoption_refuses_a_values_file_named_like_an_env_layer(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    # A UPI cluster named `prod` would move its values to values-prod.yaml: the env layer.
    await commit(
        gitlab,
        FileChange.create(
            RepoPath("sites/site1/prod/upi/prod/cluster-roles/values.yaml"), "a: 1\n"
        ),
    )
    with pytest.raises(ChangeRefusedError) as raised:
        await services.authoring.make_default(
            "redbull", "cluster-roles", DefaultsScope.UPI, jane_user, values={}, dry_run=True
        )
    assert raised.value.details["rule"] == "adoption-blocked"
    assert "env layer" in raised.value.detail
