"""The dev fixture tree loads, and seeds the fake as production lays repos out."""

from __future__ import annotations

from pathlib import Path

import pytest

from wingman_core.domain.git import AccessLevel, RepoPath
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.testing.fixtures import (
    FixtureProject,
    default_fixture_root,
    load_fixture_projects,
    seed_fake,
)


@pytest.fixture(scope="module")
def projects() -> list[FixtureProject]:
    return load_fixture_projects(
        default_fixture_root(), substitutions={"GITLAB_URL": "http://gl.test"}
    )


def test_every_production_project_is_present(projects: list[FixtureProject]) -> None:
    paths = {p.path_with_namespace for p in projects}
    assert {
        "gitops-day1/platform-config",
        "wingman/cluster-specs",
        "sigs/redbull",
        "sigs/falcon",
        "helm-charts/cluster-roles",
    } <= paths


def test_chart_urls_are_substituted(projects: list[FixtureProject]) -> None:
    redbull = next(p for p in projects if p.path_with_namespace == "sigs/redbull")
    deploy = redbull.files["operators/cluster-roles/cluster-roles.yaml"]
    assert "repourl: http://gl.test/helm-charts/cluster-roles.git" in deploy
    assert not any("{{GITLAB_URL}}" in content for p in projects for content in p.files.values())


def test_release_branches_carry_their_version(projects: list[FixtureProject]) -> None:
    chart = next(p for p in projects if p.path_with_namespace == "helm-charts/cluster-roles")
    assert chart.branches == ("2.0.0", "2.1.5-hotfix")
    assert "version: 2.1.5-hotfix" in chart.branch_files("2.1.5-hotfix")["Chart.yaml"]
    assert chart.branch_files("main") == dict(chart.files)


async def test_seed_fake_creates_projects_and_branches(projects: list[FixtureProject]) -> None:
    gitlab = InMemoryGitLab()
    seed_fake(gitlab, projects)
    day1 = await gitlab.get_project("gitops-day1/platform-config")
    clusters = await gitlab.list_tree(
        day1.id, RepoPath("sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters"), "main"
    )
    assert "ocp4-prod-herzi-site1.yaml" in [e.name for e in clusters]
    sigs = await gitlab.list_group_projects("sigs")
    assert [p.path_with_namespace for p in sigs] == [
        "sigs/falcon",
        "sigs/lynx",
        "sigs/orca",
        "sigs/redbull",
    ]
    chart = await gitlab.get_project("helm-charts/kyverno")
    assert [b.name for b in await gitlab.list_branches(chart.id)] == ["3.2.6", "3.3.0", "main"]


def test_missing_root_has_no_projects(tmp_path: Path) -> None:
    (tmp_path / "group" / "project").mkdir(parents=True)
    (tmp_path / "group" / "project" / "a.txt").write_text("a", encoding="utf-8")
    [only] = load_fixture_projects(tmp_path)
    assert only == FixtureProject("group/project", {"a.txt": "a"})


def test_access_yaml_gives_orca_a_reporter_role(projects: list[FixtureProject]) -> None:
    by_path = {p.path_with_namespace: p for p in projects}
    assert by_path["sigs/orca"].access_level is AccessLevel.REPORTER
    assert by_path["sigs/redbull"].access_level is None


async def test_seed_fake_applies_the_access_levels(projects: list[FixtureProject]) -> None:
    gitlab = InMemoryGitLab()
    seed_fake(gitlab, projects)
    orca = await gitlab.get_project("sigs/orca")
    redbull = await gitlab.get_project("sigs/redbull")
    assert await gitlab.access_level(orca.id) is AccessLevel.REPORTER
    assert await gitlab.access_level(redbull.id) is AccessLevel.OWNER


def _tree_with_access(root: Path, access: str) -> Path:
    (root / "group" / "project").mkdir(parents=True)
    (root / "group" / "project" / "a.txt").write_text("a", encoding="utf-8")
    (root / "access.yaml").write_text(access, encoding="utf-8")
    return root


def test_access_yaml_reads_role_names(tmp_path: Path) -> None:
    [only] = load_fixture_projects(_tree_with_access(tmp_path, "group/project: developer\n"))
    assert only.access_level is AccessLevel.DEVELOPER


@pytest.mark.parametrize(
    ("access", "message"),
    [("group/project: boss\n", "not a role"), ("group/ghost: reporter\n", "not fixtures")],
)
def test_access_yaml_refuses_unknown_roles_and_projects(
    tmp_path: Path, access: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        load_fixture_projects(_tree_with_access(tmp_path, access))
