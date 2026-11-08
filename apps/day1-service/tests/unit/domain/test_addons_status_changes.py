"""Addon drift, the HyperShift health rules, and the change objects day1 proposes."""

from __future__ import annotations

import pytest

from wingman_core.domain.users import Role, User
from wingman_day1.domain.addons import (
    AddonComparison,
    AddonDrift,
    AddonDriftReason,
    AddonKey,
    InstalledAddon,
    RequestedAddon,
    VersionDifference,
    compare_addons,
)
from wingman_day1.domain.changes import (
    ClusterAction,
    ClusterChange,
    SpecAction,
    SpecChange,
)
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.status import (
    Condition,
    HostedClusterObservation,
    NodePoolObservation,
    condition_problems,
    live_status,
)

ALICE = User(username="alice", role=Role.ADMIN, full_name="Alice Admin")
REF = ClusterRef("site1", "ocp4-prod-mce-site1-a", "ocp4-prod-falcon-site1")


# ── Addons ───────────────────────────────────────────────────────────────────


def test_an_addon_key_prints_as_team_slash_name() -> None:
    assert str(AddonKey("redbull", "cluster-roles")) == "redbull/cluster-roles"
    assert RequestedAddon("redbull", "cluster-roles", "main").key == AddonKey(
        "redbull", "cluster-roles"
    )


def test_a_missing_addon_carries_the_values_requested_at_create() -> None:
    expected = [RequestedAddon("redbull", "cluster-roles", "main")]
    requested = [RequestedAddon("redbull", "cluster-roles", "main", {"replicas": 3})]
    assert compare_addons(expected, [], requested=requested).missing == (
        AddonDrift("redbull", "cluster-roles", AddonDriftReason.MISSING, "main", {"replicas": 3}),
    )


def test_an_addon_at_another_version_is_reported_not_drift() -> None:
    found = compare_addons(
        [RequestedAddon("redbull", "cluster-roles", "2.1.0")],
        [InstalledAddon("redbull", "cluster-roles", "2.0.0")],
    )
    assert found.missing == ()
    assert found.version_differences == (
        VersionDifference("redbull", "cluster-roles", "2.1.0", "2.0.0"),
    )


def test_extra_installed_addons_are_not_drift() -> None:
    installed = [
        InstalledAddon("redbull", "cluster-roles", "main"),
        InstalledAddon("lynx", "backup", "1.0.0"),
    ]
    assert (
        compare_addons([RequestedAddon("redbull", "cluster-roles", "main")], installed)
        == AddonComparison()
    )


def test_an_addon_is_matched_by_team_and_name_not_name_alone() -> None:
    found = compare_addons(
        [RequestedAddon("redbull", "cluster-roles", "main")],
        [InstalledAddon("lynx", "cluster-roles", "main")],
    )
    assert [d.reason for d in found.missing] == [AddonDriftReason.MISSING]


# ── Status rules ─────────────────────────────────────────────────────────────


def test_conditions_that_hold_have_no_problems() -> None:
    conditions = [Condition("Available", "True"), Condition("Degraded", "False")]
    assert (
        condition_problems(conditions, must_be_true=["Available"], must_not_be_true=["Degraded"])
        == []
    )


def test_a_missing_or_false_required_condition_is_a_problem() -> None:
    assert condition_problems([], must_be_true=["Available"], must_not_be_true=[]) == [
        "Available: condition not found"
    ]
    problems = condition_problems(
        [Condition("Available", "False", "WaitingForEtcd", "etcd is not ready")],
        must_be_true=["Available"],
        must_not_be_true=[],
    )
    assert problems == ["Available=False reason=WaitingForEtcd msg=etcd is not ready"]


def test_a_true_forbidden_condition_is_a_problem() -> None:
    problems = condition_problems(
        [Condition("Progressing", "True", "Upgrading")],
        must_be_true=[],
        must_not_be_true=["Progressing", "Degraded"],
    )
    assert problems == ["Progressing=True reason=Upgrading msg="]


def test_live_status_applies_the_hostedcluster_and_nodepool_rules() -> None:
    hosted = HostedClusterObservation(
        name="ocp4-x",
        namespace="hcp-x",
        phase="Completed",
        version="4.18.22",
        conditions=(Condition("Available", "True"), Condition("Degraded", "True", "Bad")),
    )
    pools = [
        NodePoolObservation("x-a", 3, 2, (Condition("Ready", "True"),)),
        NodePoolObservation("x-b", 1, 1, (Condition("UpdatingConfig", "True"),)),
    ]
    status = live_status("ocp4-x", hosted, pools)
    assert (status.cluster_name, status.hosted_cluster, status.namespace) == (
        "ocp4-x",
        "ocp4-x",
        "hcp-x",
    )
    assert (status.hc_phase, status.ocp_version, status.error) == ("Completed", "4.18.22", None)
    assert status.hc_problems == ("Degraded=True reason=Bad msg=",)
    first, second = status.node_pools
    assert (first.name, first.ready_replicas, first.desired_replicas, first.problems) == (
        "x-a",
        2,
        3,
        (),
    )
    assert second.problems == (
        "Ready: condition not found",
        "UpdatingConfig=True reason= msg=",
    )


def test_a_nodepool_read_failure_is_a_hostedcluster_problem_not_silence() -> None:
    hosted = HostedClusterObservation(
        "ocp4-x", "hcp-x", None, None, (Condition("Available", "True"),)
    )
    status = live_status("ocp4-x", hosted, [], node_pool_error="403 Forbidden")
    assert status.hc_problems == ("NodePool fetch failed: 403 Forbidden",)
    assert status.node_pools == ()


# ── Changes ──────────────────────────────────────────────────────────────────


def test_a_create_carries_content_and_no_revision() -> None:
    change = ClusterChange(ClusterAction.CREATE, REF, ALICE, "why", content="a: 1\n")
    assert change.last_commit_id is None
    with pytest.raises(ValueError, match="no previous revision"):
        ClusterChange(ClusterAction.CREATE, REF, ALICE, "why", content="a", last_commit_id="abc")


def test_a_modify_or_delete_needs_the_revision_it_was_read_at() -> None:
    for action, content in ((ClusterAction.MODIFY, "a: 1\n"), (ClusterAction.DELETE, None)):
        with pytest.raises(ValueError, match="last_commit_id"):
            ClusterChange(action, REF, ALICE, "why", content=content)
        ClusterChange(action, REF, ALICE, "why", content=content, last_commit_id="a" * 40)


def test_a_delete_carries_no_content_and_a_create_needs_some() -> None:
    with pytest.raises(ValueError, match="carries no content"):
        ClusterChange(ClusterAction.DELETE, REF, ALICE, "why", content="x", last_commit_id="a")
    with pytest.raises(ValueError, match="carries no content"):
        ClusterChange(ClusterAction.CREATE, REF, ALICE, "why")


def test_spec_changes_have_the_same_invariants() -> None:
    SpecChange(SpecAction.CREATE, "s", "1.0.0", ALICE, "why", content="x")
    with pytest.raises(ValueError, match="carries no content"):
        SpecChange(SpecAction.DELETE, "s", "1.0.0", ALICE, "why", content="x", last_commit_id="a")
    with pytest.raises(ValueError, match="last_commit_id"):
        SpecChange(SpecAction.UPDATE, "s", "1.0.0", ALICE, "why", content="x")
    with pytest.raises(ValueError, match="last_commit_id"):
        SpecChange(SpecAction.DELETE, "s", "1.0.0", ALICE, "why")
