"""Of the day1 repo's files, a viewer reads a tenant cluster's alone, by its name (ADR-0068)."""

from __future__ import annotations

from wingman_core.domain.git import FileDiff, RepoPath
from wingman_day1.domain.visibility import tenant_file, viewer_diffs

MCE = "ocp4-prod-mce-site1-a"
SEED = "ocp4-prod-seed-site1-az1-a"
LARK = f"sites/site1/mces/{MCE}/hostedClusters/ocp4-prod-lark-site1.yaml"
HAWK = f"sites/site1/mces/{MCE}/hostedClusters/ocp4-prod-hawk-site1.yaml"
KV = f"sites/site1/mces/{SEED}/hostedClusters/ocp4-prod-kv-site1-az1-a.yaml"
MCE_VALUES = f"sites/site1/mces/{MCE}/values.yaml"


def _diff(old: str, new: str | None = None) -> FileDiff:
    return FileDiff(
        old_path=RepoPath(old),
        new_path=RepoPath(new or old),
        new_file=False,
        deleted_file=False,
        renamed_file=new is not None,
        diff=f"@@ {MCE} @@",
    )


def test_only_a_tenants_cluster_file_is_a_tenant_file() -> None:
    assert tenant_file(RepoPath(LARK)) is not None
    for other in (KV, MCE_VALUES, "upgrade/mces/x.yaml", "sites/site1/values.yaml"):
        assert tenant_file(RepoPath(other)) is None, other


def test_a_viewer_reads_tenants_files_by_their_file_name() -> None:
    shown = viewer_diffs([_diff(LARK), _diff(KV), _diff(MCE_VALUES), _diff(HAWK)])
    assert [str(d.new_path) for d in shown] == [
        "ocp4-prod-lark-site1.yaml",
        "ocp4-prod-hawk-site1.yaml",
    ]
    assert shown[0].diff == f"@@ {MCE} @@", "the text is the redactor's, not this rule's"


def test_one_clusters_merge_request_shows_that_clusters_file_alone() -> None:
    shown = viewer_diffs([_diff(LARK), _diff(HAWK)], cluster="ocp4-prod-hawk-site1")
    assert [str(d.old_path) for d in shown] == ["ocp4-prod-hawk-site1.yaml"]


def test_a_file_moved_out_of_a_tenants_folder_is_not_shown() -> None:
    assert viewer_diffs([_diff(LARK, MCE_VALUES)]) == []
