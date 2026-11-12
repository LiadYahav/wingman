"""Install, update, remove and bulk install: the exact commits and MRs they produce."""

from __future__ import annotations

import pytest

from wingman_core.domain.errors import RevisionConflictError
from wingman_core.domain.git import ChangeKind, FileChange, RepoPath
from wingman_core.domain.merge_request import MergeRequestRef, MRState
from wingman_core.domain.mr_conventions import (
    Repo,
    ResourceType,
    Verb,
    parse_mr_description,
    parse_mr_title,
)
from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day2.application.changes import ChangeResult, InstallSpec
from wingman_day2.application.services import Day2Services
from wingman_day2.domain.errors import (
    ChangeRefusedError,
    ChartAlreadyInstalledError,
    ChartNotInstalledError,
    UnknownChartError,
)
from wingman_day2.domain.findings import Rule
from wingman_day2.domain.yaml_values import parse_values

HERZI = "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1"
HERZI_DIR = "sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1"
PROD_MCE = "mce:site1:prod:ocp4-prod-mce-site1-a"
PREP_MCE = "mce:site1:prep:ocp4-prep-mce-site1-a"
DIDUSH = "hosted:site2:prod:ocp4-prod-mce-site2-a:ocp4-prod-didush-site2-a"


def changes(result: ChangeResult) -> list[tuple[ChangeKind, str]]:
    return [(c.kind, str(c.path)) for c in result.changes]


async def branch_files(gitlab: InMemoryGitLab, result: ChangeResult) -> dict[str, str]:
    project = await gitlab.get_project(f"sigs/{result.team}")
    return gitlab.snapshot(project.id, result.merge_request.source_branch)


async def main_files(gitlab: InMemoryGitLab, team: str) -> dict[str, str]:
    project = await gitlab.get_project(f"sigs/{team}")
    return gitlab.snapshot(project.id, "main")


async def approve(services: Day2Services, result: ChangeResult, approver: User) -> None:
    mr = result.merge_request
    await services.approvals.approve(result.team, mr.ref.iid, sha=mr.sha, approver=approver)


# ── install ─────────────────────────────────────────────────────────────────


async def test_install_writes_only_the_values_file_when_the_team_default_suffices(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    result = await services.changes.install(
        "ocp4-prod-herzi-site1",
        InstallSpec("redbull", "bmhgen", values={"replicas": 2}),
        jane_user,
    )
    mr = result.merge_request
    assert changes(result) == [(ChangeKind.CREATE, f"{HERZI_DIR}/bmhgen/values.yaml")]
    assert mr.title == "[Wingman/Day2] Install addon redbull/bmhgen on ocp4-prod-herzi-site1"
    title = parse_mr_title(mr.title)
    assert title is not None
    assert (title.repo, title.verb, title.resource_type, title.resource_name) == (
        Repo.DAY2,
        Verb.INSTALL,
        ResourceType.ADDON,
        "redbull/bmhgen",
    )
    footer = parse_mr_description(mr.description)
    assert footer is not None and (footer.author, footer.action) == ("jane", "install")
    assert set(mr.labels) == {"wingman", "day2", "install"} and mr.target_branch == "main"
    assert mr.source_branch.startswith("platform/jane/install-bmhgen-ocp4-prod-herzi-site1-")
    assert result.app_names == ("redbull-ocp4-prod-herzi-site1-bmhgen-deploy",)
    assert any("manual-sync" in note for note in result.notes)
    files = await branch_files(gitlab, result)
    assert files[f"{HERZI_DIR}/bmhgen/values.yaml"] == "replicas: 2\n"
    assert f"{HERZI_DIR}/bmhgen/values.yaml" not in await main_files(gitlab, "redbull")


async def test_install_without_a_team_default_repourl_needs_one_and_writes_it(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    with pytest.raises(ChangeRefusedError) as refused:
        await services.changes.install(HERZI, InstallSpec("redbull", "kyverno"), jane_user)
    assert refused.value.details["rule"] == str(Rule.REPOURL_MISSING)
    url = "http://gitlab.fake/helm-charts/kyverno.git"
    result = await services.changes.install(
        HERZI,
        InstallSpec("redbull", "kyverno", repourl=url, project_namespace="kyverno-hc"),
        jane_user,
    )
    assert changes(result) == [
        (ChangeKind.CREATE, f"{HERZI_DIR}/kyverno/kyverno.yaml"),
        (ChangeKind.CREATE, f"{HERZI_DIR}/kyverno/values.yaml"),
    ]
    files = await branch_files(gitlab, result)
    config, _ = parse_values(files[f"{HERZI_DIR}/kyverno/kyverno.yaml"], path="x")
    assert config == {"repourl": url, "projectNamespace": "kyverno-hc"}
    assert files[f"{HERZI_DIR}/kyverno/values.yaml"] == "{}\n"


async def test_a_chart_outside_the_catalog_needs_a_repourl(
    services: Day2Services, jane_user: User
) -> None:
    with pytest.raises(UnknownChartError):
        await services.changes.install(HERZI, InstallSpec("redbull", "cert-manager"), jane_user)
    result = await services.changes.install(
        HERZI,
        InstallSpec("redbull", "cert-manager", repourl="http://gitlab.fake/helm-charts/x.git"),
        jane_user,
    )
    assert len(result.changes) == 2


async def test_install_never_pins_a_version_unless_asked_for_an_emergency_pin(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    same = await services.changes.install(
        HERZI, InstallSpec("redbull", "bmhgen", version="HEAD"), jane_user
    )
    assert len(same.changes) == 1
    with pytest.raises(ChangeRefusedError) as refused:
        await services.changes.install(
            "ocp4-prod-karniol-site1", InstallSpec("redbull", "bmhgen", version="1.0.0"), jane_user
        )
    assert refused.value.details["rule"] == "emergency-pin-required"
    pinned = await services.changes.install(
        "ocp4-prod-karniol-site1",
        InstallSpec("redbull", "bmhgen", version="1.0.0", emergency_pin=True),
        jane_user,
    )
    assert [f.rule for f in pinned.findings] == [Rule.EMERGENCY_PIN]
    files = await branch_files(gitlab, pinned)
    folder = "sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-karniol-site1/bmhgen"
    assert files[f"{folder}/bmhgen.yaml"] == "targetRevision: 1.0.0\n"


async def test_install_refuses_a_fleet_default_on_the_same_kind_the_xor_rule(
    services: Day2Services, jane_user: User
) -> None:
    with pytest.raises(ChartAlreadyInstalledError) as refused:
        await services.changes.install(PROD_MCE, InstallSpec("falcon", "mce-agent"), jane_user)
    assert refused.value.details["rule"] == "xor"
    assert refused.value.details["tweak"] == (
        "defaults/mces/mce-agent/values-ocp4-prod-mce-site1-a.yaml"
    )


async def test_an_excluded_cluster_may_get_the_chart_in_its_own_folder(
    services: Day2Services, jane_user: User
) -> None:
    result = await services.changes.install(
        PREP_MCE,
        InstallSpec("redbull", "dhcp-api-token", repourl="http://gitlab.fake/helm-charts/x.git"),
        jane_user,
    )
    assert changes(result)[0] == (
        ChangeKind.CREATE,
        "sites/site1/prep/mces/ocp4-prep-mce-site1-a/in-cluster/dhcp-api-token/dhcp-api-token.yaml",
    )


async def test_install_refuses_what_is_installed_and_bad_names(
    services: Day2Services, jane_user: User
) -> None:
    with pytest.raises(ChartAlreadyInstalledError):
        await services.changes.install(HERZI, InstallSpec("redbull", "cluster-roles"), jane_user)
    with pytest.raises(ChangeRefusedError) as refused:
        await services.changes.install(HERZI, InstallSpec("redbull", "Bad_Name"), jane_user)
    assert refused.value.details["rule"] == "chart-name"


async def test_install_refuses_a_cluster_whose_env_is_unknown(
    services: Day2Services, jane_user: User
) -> None:
    with pytest.raises(ChangeRefusedError) as refused:
        await services.changes.install(
            "ocp4-upgrade-demo", InstallSpec("redbull", "bmhgen"), jane_user
        )
    assert refused.value.details["rule"] == str(Rule.ENV_UNKNOWN)


async def test_install_refuses_a_cluster_day1_does_not_know_a_phantom(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    day1 = (await gitlab.get_project("gitops-day1/platform-config")).id
    await gitlab.commit(
        day1,
        branch="main",
        message="drop the version",
        changes=[
            FileChange.delete(
                RepoPath(
                    "sites/site2/mces/ocp4-prod-mce-site2-a/hostedClusters/"
                    "ocp4-prod-didush-site2-a.yaml"
                )
            ),
            FileChange.create(
                RepoPath("sites/site2/mces/ocp4-prod-mce-site2-a/hostedClusters/other.yaml"),
                "mastertag: 4.16.27\n",
            ),
        ],
    )
    sigs = (await gitlab.get_project("sigs/redbull")).id
    await gitlab.commit(
        sigs,
        branch="main",
        message="a folder day1 no longer knows",
        changes=[
            FileChange.create(
                RepoPath(
                    "sites/site2/prod/mces/ocp4-prod-mce-site2-a/ocp4-prod-didush-site2-a/x/values.yaml"
                ),
                "{}\n",
            )
        ],
    )
    with pytest.raises(ChangeRefusedError) as refused:
        await services.changes.install(DIDUSH, InstallSpec("redbull", "bmhgen"), jane_user)
    assert refused.value.details["rule"] == str(Rule.DAY1_VERSION_MISSING)


async def test_installing_on_a_new_cluster_registers_it_and_says_what_else_follows(
    services: Day2Services, jane_user: User
) -> None:
    result = await services.changes.install(
        "ocp4-prod-didush-site2-a", InstallSpec("falcon", "cluster-roles"), jane_user
    )
    assert changes(result) == [
        (
            ChangeKind.CREATE,
            "sites/site2/prod/mces/ocp4-prod-mce-site2-a/ocp4-prod-didush-site2-a/"
            "cluster-roles/values.yaml",
        )
    ]
    assert any("fleet default mce-agent" in note for note in result.notes)
    assert any("syncs automatically" in note for note in result.notes)


async def test_a_change_that_adds_a_platform_error_is_refused(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    pid = (await gitlab.get_project("sigs/falcon")).id
    await gitlab.commit(
        pid,
        branch="main",
        message="a UPI folder named like a hosted cluster",
        changes=[
            FileChange.create(
                RepoPath("sites/site2/prod/upi/ocp4-prod-didush-site2-a/values.yaml"), "{}\n"
            )
        ],
    )
    with pytest.raises(ChangeRefusedError) as refused:
        await services.changes.install(DIDUSH, InstallSpec("falcon", "cluster-roles"), jane_user)
    assert refused.value.details["rule"] == str(Rule.UPI_NAME_REUSED)


# ── update ──────────────────────────────────────────────────────────────────


async def test_update_changes_the_values_file_guarded_by_the_read_commit(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    installed = (await services.installed.for_cluster(HERZI)).installed[0]
    assert installed.override.file is not None
    read_at = installed.override.file.last_commit_id
    result = await services.changes.update(
        HERZI,
        "redbull",
        "cluster-roles",
        {"groups": {"admins": ["ops"]}},
        jane_user,
        last_commit_id=read_at,
    )
    assert changes(result) == [(ChangeKind.UPDATE, f"{HERZI_DIR}/cluster-roles/values.yaml")]
    assert result.merge_request.title == (
        "[Wingman/Day2] Update addon redbull/cluster-roles on ocp4-prod-herzi-site1"
    )
    assert set(result.merge_request.labels) == {"wingman", "day2", "update"}
    files = await branch_files(gitlab, result)
    assert files[f"{HERZI_DIR}/cluster-roles/values.yaml"] == "groups:\n  admins:\n  - ops\n"


async def test_a_stale_update_conflicts_instead_of_overwriting(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    installed = (await services.installed.for_cluster(HERZI)).installed[0]
    assert installed.override.file is not None
    stale = installed.override.file.last_commit_id
    pid = (await gitlab.get_project("sigs/redbull")).id
    await gitlab.commit(
        pid,
        branch="main",
        message="someone else",
        changes=[
            FileChange.update(
                RepoPath(f"{HERZI_DIR}/cluster-roles/values.yaml"),
                "theirs: 1\n",
                last_commit_id=None,
            )
        ],
    )
    with pytest.raises(RevisionConflictError):
        await services.changes.update(
            HERZI, "redbull", "cluster-roles", {"mine": 1}, jane_user, last_commit_id=stale
        )


async def test_update_pins_only_when_asked_and_unpins_back_to_the_inherited_version(
    services: Day2Services, jane_user: User, bob_user: User
) -> None:
    with pytest.raises(ChangeRefusedError) as refused:
        await services.changes.update(
            HERZI, "redbull", "cluster-roles", {}, jane_user, version="2.0.0"
        )
    assert refused.value.details["rule"] == "emergency-pin-required"
    pin = await services.changes.update(
        HERZI, "redbull", "cluster-roles", {}, jane_user, version="2.0.0", emergency_pin=True
    )
    assert changes(pin) == [(ChangeKind.UPDATE, f"{HERZI_DIR}/cluster-roles/cluster-roles.yaml")]
    await approve(services, pin, bob_user)
    unpin = await services.changes.update(
        HERZI, "redbull", "cluster-roles", {}, jane_user, version="main"
    )
    assert changes(unpin) == [(ChangeKind.DELETE, f"{HERZI_DIR}/cluster-roles/cluster-roles.yaml")]
    with pytest.raises(ChangeRefusedError) as nothing:
        await services.changes.update(HERZI, "redbull", "cluster-roles", {}, jane_user)
    assert nothing.value.details["rule"] == "no-change"


async def test_a_fleet_default_is_tweaked_per_cluster_in_its_values_target_file(
    services: Day2Services, jane_user: User, bob_user: User
) -> None:
    result = await services.changes.update(
        PROD_MCE, "falcon", "mce-agent", {"replicas": 3}, jane_user
    )
    target = "defaults/mces/mce-agent/values-ocp4-prod-mce-site1-a.yaml"
    assert changes(result) == [(ChangeKind.CREATE, target)]
    with pytest.raises(ChangeRefusedError) as refused:
        await services.changes.update(
            PROD_MCE, "falcon", "mce-agent", {}, jane_user, version="1.0", emergency_pin=True
        )
    assert refused.value.details["rule"] == "fleet-default-pin"
    await approve(services, result, bob_user)
    cleared = await services.changes.update(PROD_MCE, "falcon", "mce-agent", {}, jane_user)
    assert changes(cleared) == [(ChangeKind.DELETE, target)]


async def test_update_of_a_chart_that_is_not_there(services: Day2Services, jane_user: User) -> None:
    with pytest.raises(ChartNotInstalledError):
        await services.changes.update(HERZI, "redbull", "bmhgen", {}, jane_user)
    with pytest.raises(RevisionConflictError):
        await services.changes.update(
            PROD_MCE, "falcon", "mce-agent", {"a": 1}, jane_user, last_commit_id="f" * 40
        )


# ── remove ──────────────────────────────────────────────────────────────────


async def test_remove_deletes_the_chart_folder_keeps_the_cluster_registered_and_says_it_orphans(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User, bob_user: User
) -> None:
    result = await services.changes.remove(HERZI, "redbull", "cluster-roles", jane_user)
    assert changes(result) == [
        (ChangeKind.DELETE, f"{HERZI_DIR}/cluster-roles/cluster-roles.yaml"),
        (ChangeKind.DELETE, f"{HERZI_DIR}/cluster-roles/values.yaml"),
        (ChangeKind.CREATE, f"{HERZI_DIR}/.gitkeep"),
    ]
    assert result.merge_request.title == (
        "[Wingman/Day2] Remove addon redbull/cluster-roles from ocp4-prod-herzi-site1"
    )
    assert any("keeps running" in note and "--cascade" in note for note in result.notes)
    assert any(".gitkeep keeps the cluster registered" in note for note in result.notes)
    assert not any("manual-sync" in note for note in result.notes)
    await approve(services, result, bob_user)
    files = await main_files(gitlab, "redbull")
    assert f"{HERZI_DIR}/.gitkeep" in files
    assert not [p for p in files if p.startswith(f"{HERZI_DIR}/cluster-roles/")]


async def test_remove_of_one_of_several_charts_adds_no_gitkeep(
    services: Day2Services, jane_user: User
) -> None:
    result = await services.changes.remove(PROD_MCE, "redbull", "kyverno", jane_user)
    assert [kind for kind, _ in changes(result)] == [ChangeKind.DELETE, ChangeKind.DELETE]


async def test_remove_refuses_a_fleet_default_and_points_at_exclusions(
    services: Day2Services, jane_user: User
) -> None:
    with pytest.raises(ChangeRefusedError) as refused:
        await services.changes.remove(PROD_MCE, "redbull", "dhcp-api-token", jane_user)
    assert refused.value.details == {
        "rule": "fleet-default-remove",
        "path": "defaults/mces/exclusions.yaml",
        "addon": "/addons/redbull/dhcp-api-token",
        "operator": "/teams/redbull/operators/dhcp-api-token",
    }


async def test_a_stale_remove_conflicts(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    redbull = (await gitlab.get_project("sigs/redbull")).id
    read_at = (await gitlab.get_branch(redbull, "main")).commit_id
    values = RepoPath(f"{HERZI_DIR}/cluster-roles/values.yaml")
    await gitlab.commit(
        redbull,
        branch="main",
        message="changed after the read",
        changes=[FileChange.update(values, "aggregateToView: false\n", last_commit_id=None)],
    )
    with pytest.raises(RevisionConflictError):
        await services.changes.remove(
            HERZI, "redbull", "cluster-roles", jane_user, last_commit_id=read_at
        )


# ── bulk ────────────────────────────────────────────────────────────────────


async def test_bulk_install_opens_one_mr_per_team(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    result = await services.changes.bulk_install(
        "ocp4-prod-hawk-site1",
        [
            InstallSpec("redbull", "bmhgen"),
            InstallSpec("redbull", "cluster-roles"),
            InstallSpec("lynx", "backup", values={"a": 1}),
        ],
        jane_user,
        message="for the hawk rollout",
    )
    assert [r.team for r in result.results] == ["redbull", "lynx"] and result.failed == ()
    redbull = result.results[0].merge_request
    assert redbull.title == (
        "[Wingman/Day2] Install addon redbull/bmhgen,cluster-roles on ocp4-prod-hawk-site1"
    )
    title = parse_mr_title(redbull.title)
    assert title is not None and title.resource_name == "redbull/bmhgen,cluster-roles"
    assert "for the hawk rollout" in redbull.description
    assert redbull.source_branch.startswith("platform/jane/install-2-charts-ocp4-prod-hawk-site1-")
    assert len(result.results[0].changes) == 2


async def test_bulk_install_validates_everything_before_opening_anything(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    with pytest.raises(ChangeRefusedError) as refused:
        await services.changes.bulk_install(
            HERZI,
            [
                InstallSpec("redbull", "bmhgen"),
                InstallSpec("redbull", "bmhgen"),
                InstallSpec("nope", "x"),
            ],
            jane_user,
        )
    problems = refused.value.details["problems"]
    assert isinstance(problems, list) and len(problems) == 2
    for team in ("redbull", "lynx"):
        pid = (await gitlab.get_project(f"sigs/{team}")).id
        assert await gitlab.list_merge_requests(pid, state=MRState.OPENED) == []


async def test_mr_numbers_are_per_team_project(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    a = await services.changes.install(HERZI, InstallSpec("redbull", "bmhgen"), jane_user)
    b = await services.changes.install(
        "ocp4-prod-hawk-site1", InstallSpec("lynx", "backup"), jane_user
    )
    assert a.merge_request.ref.iid == b.merge_request.ref.iid == 1
    assert a.merge_request.ref != b.merge_request.ref
    assert isinstance(a.merge_request.ref, MergeRequestRef)
