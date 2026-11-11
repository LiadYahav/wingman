"""Which servers are a cluster's nodes, and which of them have an uninstall run (ADR-0038)."""

from __future__ import annotations

import pytest

from wingman_day1.domain.names import HostedClusterNaming, HostedClusterRef
from wingman_day1.domain.servers import (
    UNINSTALL_HOLDER,
    RunSummary,
    ServerDetail,
    ServerRow,
    is_node_of,
    node_cluster_names,
    nodes_of,
    run_status,
    same_server_name,
    uninstall_run_ids,
    uninstall_workflow_id,
)

LARK = HostedClusterNaming().for_file("ocp4-prod-lark-site1")


def row(
    name: str, cluster: str | None, *, id_: str | None = None, reserved_by: str | None = None
) -> ServerRow:
    return ServerRow(
        id=id_ or f"srv_{name}",
        name=name,
        state="INSTALLED" if cluster else "AVAILABLE",
        health="HEALTHY",
        cluster_name=cluster,
        reserved_by=reserved_by,
    )


def test_a_cluster_is_known_to_server_scan_by_its_hosted_cluster_or_its_bare_name() -> None:
    assert HostedClusterRef("prod-lark-site1") == LARK
    assert node_cluster_names(LARK) == {"ocp4-prod-lark-site1", "prod-lark-site1"}


def test_the_sandbox_naming_gives_its_own_two_names() -> None:
    sandbox = HostedClusterNaming("").for_file("ocp4-prod-lark-site1")
    assert node_cluster_names(sandbox) == {"ocp4-ocp4-prod-lark-site1", "ocp4-prod-lark-site1"}


def test_nodes_are_the_rows_with_either_name_sorted_by_name_once_per_server() -> None:
    rows = [
        row("ocp-c", "ocp4-prod-lark-site1"),
        row("ocp-a", "prod-lark-site1"),
        row("ocp-b", "ocp4-prod-lark-site1", id_="srv_dup"),
        row("ocp-b", "ocp4-prod-lark-site1", id_="srv_dup"),
        row("ocp-other", "ocp4-prod-hawk-site1"),
        row("ocp-free", None),
        row("ocp-near", "ocp4-prod-lark-site1-a"),
    ]
    assert [n.name for n in nodes_of(rows, LARK)] == ["ocp-a", "ocp-b", "ocp-c"]


def test_two_servers_may_share_a_name_and_are_both_listed() -> None:
    rows = [row("ocp-twin", "prod-lark-site1", id_="srv_2"), row("ocp-twin", "prod-lark-site1")]
    assert [n.id for n in nodes_of(rows, LARK)] == ["srv_2", "srv_ocp-twin"]


@pytest.mark.parametrize(
    ("cluster", "expected"),
    [
        ("ocp4-prod-lark-site1", True),
        ("prod-lark-site1", True),
        ("ocp4-prod-hawk-site1", False),
        (None, False),
    ],
)
def test_a_fresh_read_places_a_server_in_the_cluster_by_either_name(
    cluster: str | None, expected: bool
) -> None:
    assert is_node_of(ServerDetail("srv_1", "ocp-a", cluster), LARK) is expected


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("ocp-dell-r660-site1-64c-DL1", True),
        ("OCP-DELL-R660-SITE1-64C-dl1", True),
        ("  ocp-dell-r660-site1-64c-DL1 ", True),
        ("ocp-dell-r660-site1-64c-DL2", False),
        ("ocp-dell-r660-site1-64c", False),
    ],
)
def test_the_confirmation_name_is_compared_ignoring_case(typed: str, expected: bool) -> None:
    assert same_server_name(typed, "ocp-dell-r660-site1-64c-DL1") is expected


def test_the_uninstall_workflow_id_is_the_lowercased_server_name() -> None:
    assert (
        uninstall_workflow_id("ocp-dell-r660-site1-64c-512gb-DL0000123")
        == "uninstall-server-from-hc-ocp-dell-r660-site1-64c-512gb-dl0000123"
    )


@pytest.mark.parametrize(("raw", "status"), [("RUNNING", "running"), ("TIMED_OUT", "timed_out")])
def test_run_statuses_are_lowercased_and_otherwise_passed_through(raw: str, status: str) -> None:
    assert run_status(raw) == status


def test_a_node_has_a_run_when_the_list_holds_its_id_or_an_uninstall_holds_it() -> None:
    listed = row("ocp-Listed", "prod-lark-site1")
    reserved = row("ocp-reserved", "prod-lark-site1", reserved_by=UNINSTALL_HOLDER)
    installing = row("ocp-installing", "prod-lark-site1", reserved_by="install-server")
    quiet = row("ocp-quiet", "prod-lark-site1")
    runs = [
        RunSummary(uninstall_workflow_id("ocp-Listed"), "failed"),
        RunSummary("uninstall-server-from-hc-somewhere-else", "running"),
    ]
    assert uninstall_run_ids([listed, reserved, installing, quiet], runs) == {
        listed.id: "uninstall-server-from-hc-ocp-listed",
        reserved.id: "uninstall-server-from-hc-ocp-reserved",
    }
