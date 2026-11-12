"""Free pods and spare servers of an MCE (ADR-0050; decisions 7 and 16 of the plan)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from wingman_day1.domain.mce_capacity import (
    ExcludedNodes,
    FreePods,
    NodeObservation,
    SpareServers,
    free_pods,
    spare_servers,
    usable,
)
from wingman_day1.domain.servers import ServerRow

MCE = "ocp4-prod-mce-site1-a"


def worker(name: str, pods: int = 250, **changes: bool) -> NodeObservation:
    return replace(NodeObservation(name, True, False, False, pods), **changes)


def test_free_pods_count_every_ready_schedulable_worker() -> None:
    nodes = [
        worker("w1"),
        worker("w2", 110),
        worker("m0", 250, control_plane=True),
        worker("m1", 250, control_plane=True, unschedulable=True),
        worker("w3", ready=False),
        worker("w4", unschedulable=True),
    ]
    pods = {"w1": 200, "w2": 30, "m0": 90, "w3": 10, "w4": 5, "gone": 7}
    assert free_pods(nodes, pods) == FreePods(
        allocatable=360,
        used=230,
        nodes_counted=2,
        excluded=ExcludedNodes(control_plane=2, not_ready=1, unschedulable=1),
    )
    assert free_pods(nodes, pods).free == 130


def test_a_node_without_pods_has_its_whole_allocation_free() -> None:
    assert free_pods([worker("w1")], {}).free == 250


def test_free_pods_never_go_below_zero() -> None:
    assert free_pods([worker("w1", 10)], {"w1": 12}).free == 0


def test_a_hub_of_control_plane_nodes_only_has_no_free_pods() -> None:
    """A compact hub (masters that are also workers) counts nothing: decision 16."""
    compact = [worker(f"m{i}", control_plane=True) for i in range(3)]
    result = free_pods(compact, {})
    assert (result.free, result.nodes_counted, result.excluded.control_plane) == (0, 0, 3)


def row(name: str, **changes: object) -> ServerRow:
    base = ServerRow(
        id=f"srv_{name}",
        name=name,
        state="INSTALLED_TO_INVENTORY",
        health="HEALTHY",
        mce=MCE,
    )
    return replace(base, **changes)


def test_spare_servers_are_registered_to_the_mce_and_in_no_cluster() -> None:
    rows = [
        row("s1"),
        row("s2", maintenance=True),
        row("s3", reachable=False),
        row("s4", stale=True),
        row("s5", health="CRITICAL"),
        row("s6", health="UNKNOWN"),
        row("s7", contested=True),
        row("s8", health="WARNING"),
        row("n1", state="INSTALLED", cluster_name="ocp4-prod-x-site1"),
        row("a1", state="AVAILABLE", mce=None),
        row("o1", mce="ocp4-prod-mce-site1-b"),
    ]
    assert spare_servers(rows, MCE) == SpareServers(total=8, usable=2)


def test_an_mce_server_scan_names_only_in_clusters_has_zero_spare() -> None:
    assert spare_servers([row("n1", state="INSTALLED")], MCE) == SpareServers(0, 0)


def test_an_mce_server_scan_never_names_is_unknown_not_zero() -> None:
    assert spare_servers([row("o1", mce="ocp4-prod-mce-site1-b")], MCE) is None
    assert spare_servers([], MCE) is None


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, True),
        ({"health": "MAJOR"}, True),
        ({"maintenance": True}, False),
        ({"health": "UNKNOWN"}, False),
        ({"contested": True}, False),
    ],
)
def test_usable(changes: dict[str, object], expected: bool) -> None:
    assert usable(row("s", **changes)) is expected
