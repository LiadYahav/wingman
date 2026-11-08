"""The dev fixture tree loads, and seeds the fake as production lays repos out."""

from __future__ import annotations

from pathlib import Path

import pytest

from wingman_core.domain.git import RepoPath
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
