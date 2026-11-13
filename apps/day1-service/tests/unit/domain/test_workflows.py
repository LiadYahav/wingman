"""The provision-cluster workflow's names: its run id and its merge request's branch (ADR-0042)."""

from __future__ import annotations

import pytest

from wingman_day1.domain.workflows import provision_branch_stem, provision_workflow_id


def test_a_run_is_named_after_the_cluster_file() -> None:
    assert (
        provision_workflow_id("ocp4-prod-rcs-site1-a") == "provision-cluster-ocp4-prod-rcs-site1-a"
    )


@pytest.mark.parametrize(
    ("branch", "stem"),
    [
        ("provision-cluster/ocp4-prod-rcs-site1-a", "ocp4-prod-rcs-site1-a"),
        ("provision-cluster/", None),
        ("provision-cluster", None),
        ("provision-cluster-ocp4-prod-rcs-site1-a", None),
        ("provision-cluster/ocp4-prod-rcs-site1-a/extra", None),
        ("platform/alice/create-cluster-ocp4-prod-rcs-site1-a-20261113T120000", None),
        ("someone/provision-cluster/ocp4-prod-rcs-site1-a", None),
        ("main", None),
    ],
)
def test_only_the_workflows_branch_names_a_cluster(branch: str, stem: str | None) -> None:
    assert provision_branch_stem(branch) == stem
