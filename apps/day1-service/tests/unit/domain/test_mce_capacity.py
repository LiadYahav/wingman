"""Free pods on the workers, servers of each node type, spare servers of an MCE (ADR-0050)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from wingman_day1.domain.machines import BMH_LABEL, INFRA_ENV_LABEL, AgentObservation
from wingman_day1.domain.mce_capacity import (
    ExcludedNodes,
    FreePods,
    NodeObservation,
    NodeTypeSupply,
    SpareServers,
    Supply,
    free_pods,
    node_type_supply,
    spare_servers,
    summed_needs,
    usable,
)
from wingman_day1.domain.servers import ServerRow
from wingman_day1.domain.status import Condition

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


def test_only_the_workers_count_infra_and_tainted_nodes_do_not() -> None:
    """A production MCE: three masters, three infra nodes (tainted HAProxy), its workers."""
    nodes = [
        *(worker(f"m{i}", control_plane=True, tainted=True) for i in range(3)),
        *(worker(f"i{i}", infra=True, tainted=True) for i in range(3)),
        worker("w0"),
        worker("w1"),
        worker("w2", tainted=True),
        worker("w3", ready=False, tainted=True),
        worker("w4", unschedulable=True, tainted=True),
        worker("w5", infra=True),
    ]
    counted = free_pods(nodes, {"w0": 100, "w1": 50, "w2": 10, "i0": 60})
    assert counted == FreePods(
        allocatable=500,
        used=150,
        nodes_counted=2,
        excluded=ExcludedNodes(control_plane=3, infra=4, not_ready=1, unschedulable=1, tainted=1),
    )


DELL = "dell-r660"
FREE = (
    Condition("Bound", "False", "Unbound"),
    Condition("Connected", "True"),
    Condition("Validated", "True"),
)


def agent(
    name: str, infra_env: str = DELL, *, approved: bool = True, bound: bool = False
) -> AgentObservation:
    conditions = FREE if not bound else (Condition("Bound", "True"), *FREE[1:])
    return AgentObservation(
        name=f"agent-{name}",
        labels={INFRA_ENV_LABEL: infra_env, BMH_LABEL: name.lower()},
        approved=approved,
        conditions=conditions,
    )


def test_needs_are_summed_per_node_type() -> None:
    assert summed_needs([(DELL, 2), ("hp", 1), (DELL, 3), ("hp", 0)]) == ((DELL, 5), ("hp", 1))


def test_free_agents_are_joined_to_server_scan_and_counted_when_healthy() -> None:
    agents = [
        agent("S1"),
        agent("s2"),
        agent("s3"),
        agent("s4", approved=False),
        agent("s5", bound=True),
        agent("s6", infra_env="hp"),
        agent("ghost"),
    ]
    rows = [row("s1"), row("s2", maintenance=True), row("s3", health="WARNING"), row("s6")]
    (dell,) = node_type_supply([(DELL, 3)], agents, rows)
    assert dell == NodeTypeSupply(DELL, 3, free_agents=4, healthy=2, not_in_server_scan=1)
    assert dell.status is Supply.UNKNOWN, "the one not in server-scan could be the third"
    assert dell.detail == "dell-r660: 2 healthy free of 3 needed (1 more free, not in server-scan)"


@pytest.mark.parametrize(
    ("supply", "status"),
    [
        (NodeTypeSupply(DELL, 3, 5, 3), Supply.ENOUGH),
        (NodeTypeSupply(DELL, 3, 5, 2), Supply.SHORT),
        (NodeTypeSupply(DELL, 3, 2, None), Supply.SHORT),
        (NodeTypeSupply(DELL, 3, 5, None), Supply.UNKNOWN),
        (NodeTypeSupply(DELL, 3, None, None), Supply.UNKNOWN),
        (NodeTypeSupply(DELL, 3, 5, 1, not_in_server_scan=2), Supply.UNKNOWN),
        (NodeTypeSupply(DELL, 3, 5, 1, not_in_server_scan=1), Supply.SHORT),
        (NodeTypeSupply(DELL, 3, 3, None, health_checked=False), Supply.ENOUGH),
        (NodeTypeSupply(DELL, 3, 2, None, health_checked=False), Supply.SHORT),
    ],
)
def test_a_node_types_status(supply: NodeTypeSupply, status: Supply) -> None:
    assert supply.status is status


def test_unread_agents_or_server_scan_leave_the_counts_unknown() -> None:
    assert node_type_supply([(DELL, 1)], None, [row("s1")]) == (
        NodeTypeSupply(DELL, 1, None, None),
    )
    assert node_type_supply([(DELL, 1)], [agent("s1")], None) == (NodeTypeSupply(DELL, 1, 1, None),)
    assert node_type_supply([(DELL, 1)], [agent("s1")], None, server_scan=False) == (
        NodeTypeSupply(DELL, 1, 1, None, health_checked=False),
    )
