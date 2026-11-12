"""Add-on authoring: new add-ons, team defaults, fleet defaults, and per-team access (ADR-0043)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial

import pytest
import yaml

from wingman_core.domain.git import AccessLevel, ChangeKind
from wingman_core.domain.mr_conventions import Verb, parse_mr_description, parse_mr_title
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day2.application.authoring import (
    UNSET,
    AuthoringResult,
    NewAddon,
    TeamDefaultEdit,
)
from wingman_day2.application.changes import InstallSpec
from wingman_day2.application.services import Day2Services
from wingman_day2.domain.clusters import DefaultsScope
from wingman_day2.domain.errors import (
    ChangeRefusedError,
    ChartAlreadyInstalledError,
    ChartNotInstalledError,
    TeamReadOnlyError,
    UnknownChartError,
)
from wingman_day2.domain.findings import Rule
from wingman_day2.domain.platform import AppSource
from wingman_day2.domain.sync_policy import PLATFORM_DEFAULT, SyncSettings
from wingman_day2.settings import FAKE_GITLAB_URL

HOSTED = DefaultsScope.HOSTED_CLUSTERS
MCES = DefaultsScope.MCES
CHART_REPO = f"{FAKE_GITLAB_URL}/helm-charts/example-chart.git"
AUTO = SyncSettings(auto_sync=True, prune=False, self_heal=True)
AUTO_NS = SyncSettings(True, False, True, ("CreateNamespace=true",))
REDBULL_HOSTED = {
    "ocp4-prep-eyal-site1": "sites/site1/prep/mces/ocp4-prep-mce-site1-a/ocp4-prep-eyal-site1",
    "ocp4-prep-itay-site1": "sites/site1/prep/mces/ocp4-prep-mce-site1-a/ocp4-prep-itay-site1",
    "ocp4-prod-herzi-site1": "sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1",
    "ocp4-prod-karniol-site1": (
        "sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-karniol-site1"
    ),
}


def files(result: AuthoringResult) -> list[tuple[ChangeKind, str]]:
    return [(c.kind, str(c.path)) for c in result.plan.changes]


async def branch_files(gitlab: InMemoryGitLab, result: AuthoringResult) -> dict[str, str]:
    assert result.merge_request is not None
    project = await gitlab.get_project(f"sigs/{result.plan.team}")
    return gitlab.snapshot(project.id, result.merge_request.source_branch)


async def merge(services: Day2Services, result: AuthoringResult, approver: User) -> None:
    mr = result.merge_request
    assert mr is not None
    await services.approvals.approve(result.plan.team, mr.ref.iid, sha=mr.sha, approver=approver)


async def confirmed(write: Callable[..., Awaitable[AuthoringResult]]) -> AuthoringResult:
    """Preview ``write``, then open it confirming exactly what the preview showed (ADR-0053)."""
    preview = await write(dry_run=True)
    return await write(
        confirm_changes=preview.plan.needs_confirmation, expected_digest=preview.plan.digest
    )


def new_addon(**overrides: object) -> NewAddon:
    fields: dict[str, object] = {
        "team": "redbull",
        "chart": "podinfo",
        "repourl": CHART_REPO,
        "sync": PLATFORM_DEFAULT,
        "project_namespace": "podinfo",
    }
    fields.update(overrides)
    return NewAddon(**fields)  # ty: ignore[invalid-argument-type]


# ── per-team access ─────────────────────────────────────────────────────────


async def test_a_team_without_write_access_gets_no_write_at_all(
    services: Day2Services, jane_user: User
) -> None:
    # sigs/orca gives Wingman Reporter only (dev/gitlab-fixtures/access.yaml).
    writes = [
        services.authoring.create(new_addon(team="orca"), jane_user),
        services.authoring.update_team_default(
            "orca", "metrics", TeamDefaultEdit(sync=AUTO), jane_user
        ),
        services.authoring.make_default("orca", "metrics", HOSTED, jane_user, values={}),
        services.authoring.update_fleet_default(
            "orca", "metrics", DefaultsScope.UPI, jane_user, values={"a": 1}
        ),
        services.changes.install("ocp4-dok-site1", InstallSpec("orca", "metrics"), jane_user),
        services.changes.bulk_install(
            "ocp4-dok-site1",
            [InstallSpec("redbull", "bmhgen"), InstallSpec("orca", "metrics")],
            jane_user,
        ),
        services.changes.update("ocp4-dok-site1", "orca", "cluster-roles", {"a": 1}, jane_user),
        services.changes.remove("ocp4-dok-site1", "orca", "cluster-roles", jane_user),
        services.approvals.reject("orca", 1),
    ]
    for write in writes:
        with pytest.raises(TeamReadOnlyError) as raised:
            await write
        assert raised.value.details == {
            "team": "orca",
            "project": "sigs/orca",
            "access_level": 20,
            "access_role": "reporter",
            "required_level": 30,
        }
        assert raised.value.detail.startswith("orca hasn't given Wingman write access to sigs/orca")


async def test_reads_still_work_and_say_why_a_team_is_read_only(services: Day2Services) -> None:
    teams = [s.team for s in (await services.topology.load()).teams]
    access = await services.access.of_all(teams)
    assert {name: a.writable for name, a in access.items()} == {
        "falcon": True,
        "lynx": True,
        "orca": False,
        "redbull": True,
    }
    assert access["orca"].reason == (
        "orca hasn't given Wingman write access to sigs/orca: Wingman's GitLab account is a "
        "Reporter there, and opening a merge request needs Developer or higher. A maintainer of "
        "sigs/orca turns writes on by adding the account to the project as a Developer."
    )
    assert [e.chart for e in await services.catalog.entries("orca")] == ["cluster-roles", "metrics"]
    defaults = await services.authoring.fleet_defaults("orca")
    assert [(d.chart, d.access.writable) for d in defaults] == [("metrics", False)]


async def test_access_is_the_higher_of_the_project_and_an_inherited_group_role(
    services: Day2Services, gitlab: InMemoryGitLab
) -> None:
    teams = {s.team.name: s.team for s in (await services.topology.load()).teams}
    gitlab.set_access_level(teams["lynx"].project.id, AccessLevel.NONE)
    lynx = await services.access.of(teams["lynx"])
    assert lynx.level is AccessLevel.NONE and "is not a member there" in (lynx.reason or "")
    # Membership of the sigs group reaches every team project: orca turns writable.
    gitlab.add_group_member("sigs", AccessLevel.DEVELOPER)
    assert (await services.access.of(teams["orca"])).level is AccessLevel.DEVELOPER


# ── create ──────────────────────────────────────────────────────────────────


async def test_create_writes_the_deploy_config_and_values_and_opens_one_mr(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    result = await services.authoring.create(
        new_addon(target_revision="0.1.0", values={"replicas": 2}), jane_user, message="for dana"
    )
    assert files(result) == [
        (ChangeKind.CREATE, "operators/podinfo/podinfo.yaml"),
        (ChangeKind.CREATE, "operators/podinfo/values.yaml"),
    ]
    branch = await branch_files(gitlab, result)
    assert branch["operators/podinfo/podinfo.yaml"] == (
        f"repourl: {CHART_REPO}\n"
        "targetRevision: 0.1.0\n"
        "projectNamespace: podinfo\n"
        "syncPolicy:\n"
        "  syncOptions:\n"
        "    - CreateNamespace=true\n"
    )
    assert yaml.safe_load(branch["operators/podinfo/values.yaml"]) == {"replicas": 2}
    mr = result.merge_request
    assert mr is not None
    assert mr.title == "[Wingman/Day2] Create addon redbull/podinfo in the team catalog"
    title = parse_mr_title(mr.title)
    assert title is not None and title.verb is Verb.CREATE
    footer = parse_mr_description(mr.description)
    assert footer is not None and (footer.author, footer.action) == ("jane", "create-addon")
    assert set(mr.labels) == {"wingman", "day2", "create-addon"}
    assert mr.source_branch.startswith("platform/jane/create-addon-podinfo-")
    assert "for dana" in mr.description and "manual sync" in result.plan.notes[0]
    assert result.plan.reach == [] and result.plan.findings == []


async def test_a_dry_run_plans_everything_and_opens_nothing(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    result = await services.authoring.create(new_addon(), jane_user, dry_run=True)
    assert result.merge_request is None and len(result.plan.changes) == 2
    redbull = await gitlab.get_project("sigs/redbull")
    assert await gitlab.list_merge_requests(redbull.id) == []


@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        ({"chart": "Pod_Info"}, "chart-name"),
        ({"repourl": "gitlab/helm-charts/x.git"}, "repourl-invalid"),
        ({"repourl": f"{FAKE_GITLAB_URL}/helm-charts/nope.git"}, "chart-repo-missing"),
        ({"target_revision": "9.9.9"}, "revision-unknown"),
        ({"project_namespace": "Pod Info"}, "namespace-invalid"),
        ({"sync": SyncSettings(prune=True)}, "sync-without-auto"),
        ({"ignore_differences": ["Secret"]}, "ignore-differences-invalid"),
    ],
)
async def test_a_new_addon_that_cannot_work_is_refused(
    services: Day2Services, jane_user: User, overrides: dict[str, object], rule: str
) -> None:
    with pytest.raises(ChangeRefusedError) as raised:
        await services.authoring.create(new_addon(**overrides), jane_user)
    assert raised.value.details["rule"] == rule


async def test_an_existing_addon_is_not_created_twice(
    services: Day2Services, jane_user: User
) -> None:
    with pytest.raises(ChartAlreadyInstalledError) as raised:
        await services.authoring.create(new_addon(chart="bmhgen"), jane_user)
    assert raised.value.details["rule"] == "addon-exists"


async def test_a_chart_repo_elsewhere_is_written_with_a_warning(
    services: Day2Services, jane_user: User
) -> None:
    result = await services.authoring.create(
        new_addon(repourl="https://charts.example.org/podinfo.git"), jane_user, dry_run=True
    )
    assert [f.rule for f in result.plan.findings] == [Rule.CHART_REPO_ELSEWHERE]


async def test_create_with_a_fleet_scope_is_one_mr_reaching_every_mce(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User, bob_user: User
) -> None:
    result = await services.authoring.create(
        new_addon(sync=AUTO, default_scope=MCES, default_values={"fleet": True}), jane_user
    )
    assert files(result) == [
        (ChangeKind.CREATE, "operators/podinfo/podinfo.yaml"),
        (ChangeKind.CREATE, "operators/podinfo/values.yaml"),
        (ChangeKind.CREATE, "defaults/mces/podinfo/values.yaml"),
    ]
    assert result.merge_request is not None
    assert result.merge_request.title == (
        "[Wingman/Day2] Create addon redbull/podinfo in the team catalog and as a fleet "
        "default on every MCE"
    )
    assert sorted(r.id for r in result.plan.reach) == [
        "mce:site1:prep:ocp4-prep-mce-site1-a",
        "mce:site1:prod:ocp4-prod-mce-site1-a",
    ]
    assert "sync by themselves" in " ".join(result.plan.notes)
    await merge(services, result, bob_user)
    charts = await services.installed.for_cluster("mce:site1:prod:ocp4-prod-mce-site1-a")
    podinfo = next(c for c in charts.installed if c.app.chart == "podinfo")
    assert podinfo.app.source is AppSource.FLEET_DEFAULT
    assert podinfo.deploy.leaf.auto_sync and podinfo.deploy.leaf.repo_url == CHART_REPO


# ── team default ────────────────────────────────────────────────────────────


async def test_editing_the_team_default_rewrites_only_what_changes(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    entry = await services.catalog.entry("redbull", "bmhgen")
    assert entry.deploy.file is not None
    result = await confirmed(
        partial(
            services.authoring.update_team_default,
            "redbull",
            "bmhgen",
            TeamDefaultEdit(
                keys={"targetRevision": "1.1.0"},
                sync=SyncSettings(True, False, True, ("CreateNamespace=true",)),
                last_commit_id=entry.deploy.file.last_commit_id,
            ),
            jane_user,
        )
    )
    assert files(result) == [(ChangeKind.UPDATE, "operators/bmhgen/bmhgen.yaml")]
    text = (await branch_files(gitlab, result))["operators/bmhgen/bmhgen.yaml"]
    assert text == (
        "projectNamespace: metal3-system\n"
        f"repourl: {FAKE_GITLAB_URL}/helm-charts/bmhgen.git\n"
        "syncPolicy:\n"
        "  syncOptions:\n"
        "    - CreateNamespace=true\n"
        "  automated:\n"
        "    prune: false\n"
        "    selfHeal: true\n"
        "targetRevision: 1.1.0\n"
    )
    assert result.merge_request is not None
    assert result.merge_request.title == "[Wingman/Day2] Update addon redbull/bmhgen team default"
    assert {r.id for r in result.plan.reach} >= {"mce:site1:prod:ocp4-prod-mce-site1-a"}
    assert "targetRevision moves to 1.1.0" in result.plan.notes[0]


async def test_setting_repourl_fixes_a_miscased_one_in_place(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    url = f"{FAKE_GITLAB_URL}/helm-charts/kyverno.git"
    result = await confirmed(
        partial(
            services.authoring.update_team_default,
            "redbull",
            "kyverno",
            TeamDefaultEdit(keys={"repourl": url}),
            jane_user,
        )
    )
    text = (await branch_files(gitlab, result))["operators/kyverno/kyverno.yaml"]
    assert text.splitlines()[1] == f"repourl: {url}" and "repoUrl" not in text


async def test_team_default_edits_that_cannot_be_written_are_refused(
    services: Day2Services, jane_user: User
) -> None:
    cases: list[tuple[str, TeamDefaultEdit, str]] = [
        ("bmhgen", TeamDefaultEdit(keys={"targetRevision": "9.9"}), "revision-unknown"),
        ("bmhgen", TeamDefaultEdit(keys={"repourl": None}), "repourl-missing"),
        ("bmhgen", TeamDefaultEdit(keys={"name": "x"}), "key-not-editable"),
        ("bmhgen", TeamDefaultEdit(sync=PLATFORM_DEFAULT), "no-change"),
        ("bmhgen", TeamDefaultEdit(values={}), "no-change"),
    ]
    for chart, edit, rule in cases:
        with pytest.raises(ChangeRefusedError) as raised:
            await services.authoring.update_team_default("redbull", chart, edit, jane_user)
        assert raised.value.details["rule"] == rule, edit
    with pytest.raises(UnknownChartError):
        await services.authoring.update_team_default(
            "redbull", "ghost", TeamDefaultEdit(sync=AUTO), jane_user
        )


async def test_team_default_values_are_replaced_guarded(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    result = await confirmed(
        partial(
            services.authoring.update_team_default,
            "redbull",
            "bmhgen",
            TeamDefaultEdit(values={"replicas": 3}),
            jane_user,
        )
    )
    assert files(result) == [(ChangeKind.UPDATE, "operators/bmhgen/values.yaml")]
    assert result.plan.changes[0].last_commit_id


# ── make default ────────────────────────────────────────────────────────────


async def test_making_a_default_moves_cluster_folders_into_it_with_the_same_apps(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User, bob_user: User
) -> None:
    before = (await services.topology.load()).team("redbull").plan
    hosted_before = {(a.ref.id, a.generator_app) for a in before.apps if a.chart == "cluster-roles"}
    result = await services.authoring.make_default(
        "redbull", "cluster-roles", HOSTED, jane_user, values={}
    )
    plan = result.plan
    assert sorted(a.ref.name for a in plan.adopted) == sorted(REDBULL_HOSTED)
    assert all(a.changes == () and a.moved == () for a in plan.adopted)
    assert plan.needs_confirmation == []
    expected = {(ChangeKind.CREATE, "defaults/hosted-clusters/cluster-roles/values.yaml")}
    for folder in REDBULL_HOSTED.values():
        expected |= {
            (ChangeKind.DELETE, f"{folder}/cluster-roles/cluster-roles.yaml"),
            (ChangeKind.DELETE, f"{folder}/cluster-roles/values.yaml"),
            (ChangeKind.CREATE, f"{folder}/.gitkeep"),
        }
    assert set(files(result)) == expected
    assert result.merge_request is not None
    assert result.merge_request.title == (
        "[Wingman/Day2] Promote addon redbull/cluster-roles to a fleet default on every hosted "
        "cluster"
    )
    assert set(result.merge_request.labels) == {"wingman", "day2", "make-default"}
    assert "Nothing is orphaned" in " ".join(plan.notes)
    await merge(services, result, bob_user)
    after = (await services.topology.load()).team("redbull")
    moved = {(a.ref.id, a.generator_app) for a in after.plan.apps if a.chart == "cluster-roles"}
    # Same wrapper apps on the same hosted clusters: ArgoCD keeps them (the UPI one stays too).
    assert moved == hosted_before
    assert {
        a.source
        for a in after.plan.apps
        if a.chart == "cluster-roles" and a.ref.kind.value == "hosted"
    } == {AppSource.FLEET_DEFAULT}
    assert after.findings == ()


async def test_a_move_that_changes_a_cluster_needs_its_confirmation(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    install = await services.changes.install(
        "ocp4-prod-herzi-site1", InstallSpec("redbull", "bmhgen", values={"replicas": 1}), jane_user
    )
    await services.approvals.approve(
        "redbull",
        install.merge_request.ref.iid,
        sha=install.merge_request.sha,
        approver=User("bob", jane_user.role),
    )
    plan = (
        await services.authoring.make_default(
            "redbull",
            "bmhgen",
            HOSTED,
            jane_user,
            values={"replicas": 2},
            sync=AUTO_NS,
            dry_run=True,
        )
    ).plan
    herzi = "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1"
    assert plan.needs_confirmation == [herzi]
    (adoption,) = plan.adopted
    folder = REDBULL_HOSTED["ocp4-prod-herzi-site1"]
    assert [(str(a), str(b)) for a, b in adoption.moved] == [
        (
            f"{folder}/bmhgen/values.yaml",
            "defaults/hosted-clusters/bmhgen/values-ocp4-prod-herzi-site1.yaml",
        )
    ]
    assert [(c.stack, c.key, c.before, c.after) for c in adoption.changes] == [
        ("deploy", "syncPolicy.automated.prune", None, False),
        ("deploy", "syncPolicy.automated.selfHeal", None, True),
    ]
    with pytest.raises(ChangeRefusedError) as raised:
        await services.authoring.make_default(
            "redbull", "bmhgen", HOSTED, jane_user, values={"replicas": 2}, sync=AUTO_NS
        )
    assert raised.value.details["rule"] == "confirm-changes"
    assert raised.value.details["needs_confirmation"] == [herzi]
    result = await services.authoring.make_default(
        "redbull",
        "bmhgen",
        HOSTED,
        jane_user,
        values={"replicas": 2},
        sync=AUTO_NS,
        confirm_changes=[herzi],
        expected_digest=plan.digest,
    )
    branch = await branch_files(gitlab, result)
    # The cluster's values moved byte for byte, so it keeps replicas: 1 over the fleet's 2.
    assert branch["defaults/hosted-clusters/bmhgen/values-ocp4-prod-herzi-site1.yaml"] == (
        "replicas: 1\n"
    )
    assert yaml.safe_load(branch["defaults/hosted-clusters/bmhgen/bmhgen.yaml"]) == {
        "syncPolicy": {"automated": {"prune": False, "selfHeal": True}}
    }


async def test_make_default_refusals(services: Day2Services, jane_user: User) -> None:
    with pytest.raises(ChartAlreadyInstalledError) as raised:
        await services.authoring.make_default("falcon", "mce-agent", MCES, jane_user, values={})
    assert raised.value.details["rule"] == "default-exists"
    with pytest.raises(UnknownChartError):
        await services.authoring.make_default("redbull", "ghost", MCES, jane_user, values={})
    with pytest.raises(ChangeRefusedError) as refused:
        await services.authoring.make_default(
            "redbull", "cluster-roles", HOSTED, jane_user, values={}, confirm_changes=["x"]
        )
    assert refused.value.details["rule"] == "confirm-changes"


async def test_the_hub_default_is_the_hubs_own_folder(
    services: Day2Services, jane_user: User
) -> None:
    result = await services.authoring.make_default(
        "redbull", "bmhgen", DefaultsScope.HUB, jane_user, values={}, dry_run=True
    )
    assert [r.id for r in result.plan.reach] == ["hub"] and result.plan.adopted == []


# ── fleet defaults ──────────────────────────────────────────────────────────


async def test_fleet_defaults_are_listed_with_their_reach_and_sync(
    services: Day2Services,
) -> None:
    found = {(d.chart, str(d.scope)): d for d in await services.authoring.fleet_defaults("redbull")}
    assert sorted(found) == [
        ("dhcp-api-token", "mces"),
        ("example-chart", "hub"),
        ("example-chart", "mces"),
    ]
    token = found[("dhcp-api-token", "mces")]
    assert not token.in_catalog and token.sync_overridden
    assert token.sync == SyncSettings(True, True, True, ("CreateNamespace=true",))
    assert [r.id for r in token.reach] == ["mce:site1:prod:ocp4-prod-mce-site1-a"]
    assert [r.id for r in token.excluded] == ["mce:site1:prep:ocp4-prep-mce-site1-a"]
    example = found[("example-chart", "mces")]
    assert [str(p) for p in example.tweaks] == [
        "defaults/mces/example-chart/values-ocp4-prep-mce-site1-a.yaml"
    ]
    assert example.last_commit_id


async def test_a_fleet_default_sync_edit_keeps_every_comment(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    path = "defaults/mces/dhcp-api-token/dhcp-api-token.yaml"
    redbull = await gitlab.get_project("sigs/redbull")
    old = gitlab.snapshot(redbull.id, "main")[path]
    result = await confirmed(
        partial(
            services.authoring.update_fleet_default,
            "redbull",
            "dhcp-api-token",
            MCES,
            jane_user,
            sync=SyncSettings(True, False, True, ("CreateNamespace=true",)),
        )
    )
    new = (await branch_files(gitlab, result))[path]
    assert [line for line in old.splitlines() if line not in new.splitlines()] == [
        "    prune: true"
    ]
    assert [line for line in new.splitlines() if line not in old.splitlines()] == [
        "    prune: false"
    ]
    assert result.merge_request is not None
    assert result.merge_request.title == (
        "[Wingman/Day2] Update addon redbull/dhcp-api-token fleet default on every MCE"
    )


async def test_a_fleet_default_goes_back_to_the_team_default_sync(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    result = await confirmed(
        partial(
            services.authoring.update_fleet_default,
            "redbull",
            "example-chart",
            MCES,
            jane_user,
            sync=None,
            values={"fleet": True},
        )
    )
    branch = await branch_files(gitlab, result)
    assert yaml.safe_load(branch["defaults/mces/example-chart/example-chart.yaml"]) == {
        "projectNamespace": "example-namespace",
        "repourl": f"{FAKE_GITLAB_URL}/helm-charts/example-chart.git",
        "targetRevision": "main",
    }
    assert yaml.safe_load(branch["defaults/mces/example-chart/values.yaml"]) == {"fleet": True}


async def test_fleet_default_edit_refusals(services: Day2Services, jane_user: User) -> None:
    with pytest.raises(ChartNotInstalledError):
        await services.authoring.update_fleet_default(
            "redbull", "bmhgen", MCES, jane_user, values={"a": 1}
        )
    with pytest.raises(ChangeRefusedError) as raised:
        await services.authoring.update_fleet_default(
            "redbull", "example-chart", MCES, jane_user, sync=UNSET
        )
    assert raised.value.details["rule"] == "no-change"


# ── template ────────────────────────────────────────────────────────────────


async def test_the_template_copies_the_teams_usual_sync_options_and_repo_folder(
    services: Day2Services,
) -> None:
    redbull = await services.authoring.template("redbull")
    assert redbull.sync == PLATFORM_DEFAULT and "3 of 3" in redbull.sync_source
    assert redbull.repourl_prefix == f"{FAKE_GITLAB_URL}/helm-charts/"
    scopes = {str(s.scope): [r.id for r in s.destinations] for s in redbull.scopes}
    assert len(scopes["hosted-clusters"]) == 4 and scopes["hub"] == ["hub"]
    assert redbull.access.writable
    falcon = await services.authoring.template("falcon")
    assert falcon.sync == SyncSettings(auto_sync=True, prune=False, self_heal=True)
    orca = await services.authoring.template("orca")
    assert not orca.access.writable
