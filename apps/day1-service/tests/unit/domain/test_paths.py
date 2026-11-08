"""Repository paths: the day1 layout, and names that must never leave their folder."""

from __future__ import annotations

import pytest

from wingman_core.domain.errors import InvalidRepoPathError
from wingman_core.domain.git import RepoPath
from wingman_day1.domain import paths
from wingman_day1.domain.paths import ClusterRef, HostedClustersEntry


def test_a_cluster_file_lives_under_its_mces_hosted_clusters_folder() -> None:
    ref = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-herzi-site1")
    assert ref.path == RepoPath(
        "sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-herzi-site1.yaml"
    )


def test_the_layout_helpers_build_the_argocd_value_layers() -> None:
    assert paths.site_dir("site1") == RepoPath("sites/site1")
    assert paths.mce_dir("site1", "m") == RepoPath("sites/site1/mces/m")
    assert paths.mce_values("site1", "m") == RepoPath("sites/site1/mces/m/values.yaml")
    assert paths.mce_version("site1", "m") == RepoPath("sites/site1/mces/m/version.yaml")
    assert paths.hosted_clusters_dir("s", "m") == RepoPath("sites/s/mces/m/hostedClusters")


@pytest.mark.parametrize("name", ["..", ".", "a/b", "", "../etc"])
def test_a_name_from_a_request_cannot_escape_its_folder(name: str) -> None:
    with pytest.raises(InvalidRepoPathError):
        paths.mce_dir(name, "m")
    with pytest.raises(InvalidRepoPathError):
        paths.mce_dir("site1", name)
    with pytest.raises(InvalidRepoPathError):
        paths.site_dir(name)


def test_a_cluster_name_with_a_slash_cannot_reach_another_folder() -> None:
    with pytest.raises(InvalidRepoPathError):
        _ = ClusterRef("site1", "m", "../../x").path


def test_hosted_clusters_paths_are_recognised() -> None:
    entry = paths.parse_hosted_clusters_path(
        RepoPath("sites/site1/mces/m/hostedClusters/ocp4-prod-x-site1.yaml")
    )
    assert entry == HostedClustersEntry("site1", "m", "ocp4-prod-x-site1.yaml")
    assert entry.cluster == ClusterRef("site1", "m", "ocp4-prod-x-site1")


@pytest.mark.parametrize(
    "path",
    [
        "sites/site1/mces/m/values.yaml",
        "sites/site1/mces/m/hostedClusters",
        "sites/site1/mces/m/other/x.yaml",
        "sites/site1/clusters/m/hostedClusters/x.yaml",
        "other/site1/mces/m/hostedClusters/x.yaml",
        "sites/site1/mces/m/hostedClusters/nested/x.yaml",
    ],
)
def test_other_paths_are_not_hosted_clusters_entries(path: str) -> None:
    assert paths.parse_hosted_clusters_path(RepoPath(path)) is None


@pytest.mark.parametrize("filename", [".gitkeep", "x.wingman.yaml", "x.yml", ".yaml", "README"])
def test_files_that_are_not_name_dot_yaml_are_stray_not_clusters(filename: str) -> None:
    assert HostedClustersEntry("site1", "m", filename).cluster is None


def test_spec_files_live_under_the_specs_root() -> None:
    assert paths.spec_file("specs", "agent-single") == RepoPath("specs/agent-single.yaml")
    assert paths.spec_file("catalog/specs", "x") == RepoPath("catalog/specs/x.yaml")
    with pytest.raises(InvalidRepoPathError):
        paths.spec_file("specs", "../x")
    assert RepoPath("cluster-template.j2") == paths.TEMPLATE_FILE


def test_upgrade_rules_live_in_the_day1_repo_upgrade_folder() -> None:
    assert RepoPath("upgrade/ladder.yaml") == paths.UPGRADE_LADDER
    assert paths.upgrade_mce_rules("ocp4-prod-mce-site1-a") == RepoPath(
        "upgrade/mces/ocp4-prod-mce-site1-a.yaml"
    )
    with pytest.raises(InvalidRepoPathError):
        paths.upgrade_mce_rules("../x")
