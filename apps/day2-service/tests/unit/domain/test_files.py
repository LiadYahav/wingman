"""The repo tree, YAML value files, versions and deploy configs."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from wingman_core.domain.git import FileChange, RepoPath
from wingman_day2.domain.clusters import ClusterRef
from wingman_day2.domain.day1 import build_day1_index, day1_version_files
from wingman_day2.domain.deploy_config import leaf_application, miscased_repourl_keys, truthy
from wingman_day2.domain.tree import RepoTree
from wingman_day2.domain.versions import mastertag_problem, ocp_version, read_version_file
from wingman_day2.domain.yaml_values import dump_values, parse_values, parse_yaml

HOSTED = ClusterRef.hosted("site1", "prod", "m", "c")


# ── tree ────────────────────────────────────────────────────────────────────


def test_directories_exist_exactly_when_a_file_is_below_them() -> None:
    tree = RepoTree.of(["a/b/c.yaml", "a/d/.gitkeep", "e.yaml"])
    assert tree.is_dir(RepoPath("a/b")) and tree.is_dir(RepoPath("a/d"))
    assert not tree.is_dir(RepoPath("a/x"))
    assert tree.is_dir(RepoPath.root())
    assert tree.is_file(RepoPath("e.yaml")) and not tree.is_file(RepoPath("a"))


def test_subdirs_is_one_segment_and_skips_hidden_folders() -> None:
    tree = RepoTree.of(["s/a/x/f", "s/b/f", "s/.hidden/f", "s/file", ".git/x/f"])
    assert tree.subdirs(RepoPath("s")) == ["a", "b"]
    assert tree.subdirs(RepoPath.root()) == ["s"]
    assert tree.subdirs(RepoPath("s/.hidden")) == []
    assert tree.subdirs(RepoPath("missing")) == []


def test_files_under_includes_hidden_files() -> None:
    tree = RepoTree.of(["c/x/values.yaml", "c/x/.gitkeep", "c/y/values.yaml"])
    assert [str(p) for p in tree.files_under(RepoPath("c/x"))] == [
        "c/x/.gitkeep",
        "c/x/values.yaml",
    ]


def test_with_changes_adds_removes_and_moves() -> None:
    tree = RepoTree.of(["a/one", "a/two", "b/three"])
    after = tree.with_changes(
        [
            FileChange.create(RepoPath("c/new"), "x"),
            FileChange.delete(RepoPath("b/three")),
            FileChange.move(RepoPath("a/two"), RepoPath("d/two")),
            FileChange.update(RepoPath("a/one"), "y", last_commit_id=None),
        ]
    )
    assert after.files == {"a/one", "c/new", "d/two"}
    assert not after.is_dir(RepoPath("b"))


@given(st.lists(st.from_regex(r"[a-c](/[a-c]){0,3}", fullmatch=True), max_size=12))
def test_every_parent_of_a_file_is_a_directory(paths: list[str]) -> None:
    tree = RepoTree.of(paths)
    for path in tree.files:
        parent = RepoPath(path).parent
        while not parent.is_root:
            assert tree.is_dir(parent)
            parent = parent.parent


# ── YAML ────────────────────────────────────────────────────────────────────


def test_values_files_parse_like_helm_reads_them() -> None:
    assert parse_values("", path="v") == ({}, None)
    assert parse_values("a: 1\nwhen: 2026-01-01\n", path="v") == (
        {"a": 1, "when": "2026-01-01"},
        None,
    )
    values, problem = parse_values("- a\n", path="v")
    assert values == {} and problem is not None and "mapping" in problem.message
    _, problem = parse_values("a: [\n", path="p.yaml")
    assert problem is not None and problem.path == "p.yaml" and problem.line == 2


def test_parse_yaml_reports_a_second_document() -> None:
    _, problem = parse_yaml("a: 1\n---\nb: 2\n", path="x")
    assert problem is not None


def test_dump_values_round_trips_and_writes_an_empty_map_explicitly() -> None:
    assert dump_values({}) == "{}\n"
    values = {"replicas": 2, "nested": {"key": "v", "list": [1, "two"]}}
    assert parse_values(dump_values(values), path="v") == (values, None)


# ── versions ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("tag", "version"),
    [("4.16.27-x86_64", "4.16.27"), ("4.20.9", "4.20.9"), ("4.19.10-multi-arch", "4.19.10")],
)
def test_the_platform_strips_the_arch_at_the_first_dash(tag: str, version: str) -> None:
    assert ocp_version(tag) == version
    assert mastertag_problem(tag) is None


@pytest.mark.parametrize("tag", ["4.16", "latest", "4.16.x", 4.16])
def test_a_mastertag_without_a_full_version_is_a_problem(tag: object) -> None:
    assert mastertag_problem(tag) is not None


def test_version_files() -> None:
    assert read_version_file("# just a comment\n", path="v").mastertag is None
    plain = read_version_file("mastertag: 4.16.27-x86_64\n", path="v")
    assert (plain.ocp_version, plain.problem, plain.extra_keys) == ("4.16.27", None, ())
    extra = read_version_file("mastertag: 4.16.27\nreplicas: 3\n", path="v")
    assert extra.extra_keys == ("replicas",) and extra.ocp_version == "4.16.27"
    missing = read_version_file("other: 1\n", path="v")
    assert missing.mastertag is None and missing.problem == "no top-level mastertag"
    assert read_version_file("- 1\n", path="v").problem is not None
    broken = read_version_file("mastertag: [\n", path="v")
    assert broken.yaml_problem is not None and broken.ocp_version is None


# ── deploy config → leaf ────────────────────────────────────────────────────


def test_the_leaf_defaults_like_deploy_app_yaml() -> None:
    leaf = leaf_application({"repourl": "https://g/x.git"}, team="t", chart="x", ref=HOSTED)
    assert leaf.name == "t-c-x-deploy"
    assert (leaf.target_revision, leaf.path, leaf.release_name) == ("HEAD", ".", "x")
    assert (leaf.destination, leaf.destination_namespace, leaf.namespace) == ("c", None, "gitops-t")
    assert leaf.argo == "m" and leaf.sync_policy is None and not leaf.auto_sync


def test_repo_url_is_only_read_lowercase() -> None:
    leaf = leaf_application({"repoUrl": "https://g/x.git"}, team="t", chart="x", ref=HOSTED)
    assert leaf.repo_url == ""
    assert miscased_repourl_keys({"repoUrl": 1, "repoURL": 2, "repourl": 3}) == [
        "repoURL",
        "repoUrl",
    ]


def test_the_leaf_honours_every_deploy_key() -> None:
    merged = {
        "repourl": "u",
        "targetRevision": "1.2.3",
        "path": "charts/x",
        "projectNamespace": "ns",
        "syncPolicy": {"automated": {"selfHeal": True}},
        "ignoreDifferences": [{"kind": "Secret"}],
        "appname": "custom",
        "oldConvention": True,
    }
    leaf = leaf_application(merged, team="t", chart="x", ref=ClusterRef.mce_hub("s", "prod", "m"))
    assert leaf.name == "custom"
    assert (leaf.target_revision, leaf.path, leaf.destination_namespace) == (
        "1.2.3",
        "charts/x",
        "ns",
    )
    assert leaf.release_name == "in-cluster-t-x" and leaf.destination == "in-cluster"
    assert leaf.auto_sync and leaf.ignore_differences == [{"kind": "Secret"}]


def test_upi_leaves_live_on_the_upi_argo() -> None:
    leaf = leaf_application({}, team="t", chart="x", ref=ClusterRef.upi("s", "prod", "u"))
    assert (leaf.namespace, leaf.argo, leaf.destination) == (
        "openshift-gitops-upi",
        "prod-hub-upi",
        "u",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        (False, False),
        (0, False),
        ("", False),
        ({}, False),
        ([], False),
        ("x", True),
        (1, True),
        (object(), True),
    ],
)
def test_go_template_truthiness(value: object, expected: bool) -> None:
    assert truthy(value) is expected
    assert (
        str(
            leaf_application(
                {"targetRevision": False}, team="t", chart="x", ref=HOSTED
            ).target_revision
        )
        == "HEAD"
    )


# ── the day1 index ──────────────────────────────────────────────────────────


def test_the_day1_index_reads_hosted_clusters_as_day1_does() -> None:
    # A dotted stem is not a cluster name: day1 reports the legacy
    # <cluster>.wingman.yaml sidecar as stray, so day2 must not list a
    # hosted cluster "falcon.wingman" either.
    folder = "sites/site1/mces/m/hostedClusters"
    tree = RepoTree.of(
        [
            f"{folder}/ocp4-prod-falcon-site1.yaml",
            f"{folder}/ocp4-prod-falcon-site1.wingman.yaml",
            f"{folder}/.yaml",
            f"{folder}/notes.txt",
            f"{folder}/nested/ocp4-prod-lynx-site1.yaml",
        ]
    )
    index = build_day1_index(tree, {})
    assert list(index.hosted) == [("site1", "m", "ocp4-prod-falcon-site1")]
    assert [str(p) for p in day1_version_files(tree)] == [f"{folder}/ocp4-prod-falcon-site1.yaml"]
