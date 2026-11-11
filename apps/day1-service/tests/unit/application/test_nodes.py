"""A cluster's nodes from server-scan and their uninstall runs; starting an uninstall (ADR-0038).

Built with ``create_app`` on the fakes, so the caches main.py puts in front of
server-scan and the orchestrator are the ones tested.
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI

from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.application.nodes import UNINSTALL_NOT_CONFIGURED, NodeService
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    InvalidInputError,
    NodeNotInClusterError,
    ServerNotFoundError,
    ServerScanUnavailableError,
    UninstallAlreadyRunningError,
    WorkflowsNotConfiguredError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.servers import UNINSTALL_HOLDER, RunSummary, ServerRow
from wingman_day1.domain.workflows import WorkflowRun
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory, FakeUninstallWorkflow
from wingman_day1.ports import UninstallWorkflow

MCE = "ocp4-prod-mce-site1-a"
LARK = ClusterRef("site1", MCE, "ocp4-prod-lark-site1")
HAWK = "ocp4-prod-hawk-site1"
UI = "https://server-scan.example"


def server(suffix: str, cluster: str | None = "ocp4-prod-lark-site1", **extra: Any) -> ServerRow:
    row = ServerRow(
        id=f"srv_{suffix.lower()}",
        name=f"ocp-dell-r660-site1-64c-512gb-{suffix}",
        state="INSTALLED" if cluster else "AVAILABLE",
        health="HEALTHY",
        cluster_name=cluster,
        mce=MCE if cluster else None,
    )
    return dataclasses.replace(row, **extra)


A, B, C = server("DLFAKE0003"), server("DLFAKE0001", "prod-lark-site1"), server("DLFAKE0002")
ELSEWHERE, FREE = server("DLFAKE0009", HAWK), server("DLFAKE0010", None)


class FixedClock:
    def __call__(self) -> datetime:
        return datetime(2026, 11, 11, 8, 0, tzinfo=UTC)


class StubWorkflow:
    """An orchestrator whose list and runs are given: a run the list misses, a vanished run."""

    def __init__(self, listed: list[RunSummary], runs: dict[str, WorkflowRun]) -> None:
        self._listed = listed
        self._runs = runs

    async def runs(self) -> list[RunSummary]:
        return self._listed

    async def run(self, workflow_id: str) -> WorkflowRun | None:
        return self._runs.get(workflow_id)

    async def start(self, *, server_name: str, mce: str, namespace: str | None) -> WorkflowRun:
        raise AssertionError("not started in these tests")


@pytest.fixture
def inventory() -> FakeServerInventory:
    return FakeServerInventory([A, B, C, ELSEWHERE, FREE])


@pytest.fixture
def workflow(inventory: FakeServerInventory) -> FakeUninstallWorkflow:
    return FakeUninstallWorkflow(inventory, clock=FixedClock())


def build(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    inventory: FakeServerInventory,
    uninstall: UninstallWorkflow | None,
    **settings: object,
) -> FastAPI:
    return support.build_app(
        gitlab=gitlab,
        hub=None,
        identity=None,
        day2=FakeDay2Addons(),
        clock=clock,
        inventory=inventory,
        uninstall=uninstall,
        SERVER_SCAN_UI_URL=UI,
        **settings,
    )


def nodes_of(app: FastAPI) -> NodeService:
    service = app.state.day1.nodes
    assert isinstance(service, NodeService)
    return service


@pytest.fixture
def nodes(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    inventory: FakeServerInventory,
    workflow: FakeUninstallWorkflow,
) -> NodeService:
    return nodes_of(build(support, gitlab, clock, inventory, workflow))


# ── Listing ──────────────────────────────────────────────────────────────────


async def test_nodes_are_the_clusters_servers_by_either_name_sorted_with_links(
    nodes: NodeService,
) -> None:
    found = await nodes.nodes(LARK)
    assert found.hosted_cluster == "ocp4-prod-lark-site1"
    assert [n.server.name for n in found.nodes] == [B.name, C.name, A.name]
    assert found.nodes[0].url == f"{UI}/servers/{B.id}"
    assert (found.uninstall_available, found.uninstall_detail, found.runs_error) == (
        True,
        None,
        None,
    )
    assert all(n.uninstall is None for n in found.nodes)


async def test_a_cluster_server_scan_knows_no_server_of_has_no_nodes(nodes: NodeService) -> None:
    herzi = await nodes.nodes(ClusterRef("site1", MCE, "ocp4-prod-herzi-site1"))
    assert (herzi.hosted_cluster, herzi.nodes) == ("ocp4-prod-herzi-site1", ())


async def test_a_node_shows_its_newest_run_with_the_workflows_own_phase_and_error(
    support: Any, gitlab: InMemoryGitLab, clock: Any, inventory: FakeServerInventory
) -> None:
    failed = WorkflowRun(
        f"uninstall-server-from-hc-{C.name.lower()}",
        "failed",
        phase="some-new-phase",
        error="ClusterMembershipMismatchError: the MCE disagrees",
    )
    seeded = FakeUninstallWorkflow(inventory, clock=FixedClock(), runs=[failed])
    found = await nodes_of(build(support, gitlab, clock, inventory, seeded)).nodes(LARK)
    assert {n.server.id: n.uninstall for n in found.nodes} == {B.id: None, C.id: failed, A.id: None}


async def test_a_run_the_list_misses_is_found_through_server_scans_lock(
    support: Any, gitlab: InMemoryGitLab, clock: Any, inventory: FakeServerInventory
) -> None:
    inventory.replace(dataclasses.replace(A, reserved_by=UNINSTALL_HOLDER))
    old = WorkflowRun(f"uninstall-server-from-hc-{A.name.lower()}", "running", phase="draining")
    stub = StubWorkflow([], {old.workflow_id: old})
    found = await nodes_of(build(support, gitlab, clock, inventory, stub)).nodes(LARK)
    assert {n.server.id: n.uninstall for n in found.nodes}[A.id] == old


async def test_a_listed_run_that_cannot_be_read_alone_keeps_its_listed_status(
    support: Any, gitlab: InMemoryGitLab, clock: Any, inventory: FakeServerInventory
) -> None:
    workflow_id = f"uninstall-server-from-hc-{B.name.lower()}"
    stub = StubWorkflow(
        [RunSummary(workflow_id, "completed"), RunSummary(workflow_id, "failed")], {}
    )
    found = await nodes_of(build(support, gitlab, clock, inventory, stub)).nodes(LARK)
    assert found.nodes[0].uninstall == WorkflowRun(workflow_id, "completed")


async def test_an_unreadable_orchestrator_leaves_the_nodes_and_says_runs_are_unknown(
    nodes: NodeService, workflow: FakeUninstallWorkflow
) -> None:
    workflow.unavailable = True
    found = await nodes.nodes(LARK)
    assert len(found.nodes) == 3
    assert all(n.uninstall is None for n in found.nodes)
    assert found.runs_error == "WorkflowsUnavailable: the orchestrator is unreachable (fake)"
    assert found.uninstall_available, "the orchestrator is configured; it did not answer"


async def test_without_an_orchestrator_nodes_are_listed_and_uninstall_is_not_offered(
    support: Any, gitlab: InMemoryGitLab, clock: Any, inventory: FakeServerInventory
) -> None:
    service = nodes_of(build(support, gitlab, clock, inventory, None))
    found = await service.nodes(LARK)
    assert len(found.nodes) == 3
    assert (found.uninstall_available, found.uninstall_detail, found.runs_error) == (
        False,
        UNINSTALL_NOT_CONFIGURED,
        None,
    )
    with pytest.raises(WorkflowsNotConfiguredError, match="WORKFLOWS_API_URL"):
        await service.uninstall(LARK, A.id, server_name=A.name, user=support.ALICE)


async def test_server_scan_down_is_an_error_never_an_empty_list(
    nodes: NodeService, inventory: FakeServerInventory
) -> None:
    inventory.unavailable = True
    with pytest.raises(ServerScanUnavailableError):
        await nodes.nodes(LARK)


# ── Uninstall ────────────────────────────────────────────────────────────────


async def test_an_uninstall_starts_the_workflow_on_the_clusters_mce_and_logs_who(
    nodes: NodeService, workflow: FakeUninstallWorkflow, support: Any, caplog: Any
) -> None:
    caplog.set_level(logging.INFO, logger="wingman_day1.application.nodes")
    run = await nodes.uninstall(LARK, A.id, server_name=A.name.lower(), user=support.ALICE)
    workflow_id = f"uninstall-server-from-hc-{A.name.lower()}"
    assert run == WorkflowRun(workflow_id, "running")
    assert workflow.starts == [{"server_name": A.name, "mce": MCE, "namespace": None}]
    (record,) = [r for r in caplog.records if getattr(r, "event", None)]
    assert record.levelno == logging.INFO
    assert {
        k: getattr(record, k)
        for k in ("event", "user", "cluster", "mce", "server_id", "server_name", "workflow_id")
    } == {
        "event": "node_uninstall_started",
        "user": support.ALICE.username,
        "cluster": LARK.name,
        "mce": MCE,
        "server_id": A.id,
        "server_name": A.name,
        "workflow_id": workflow_id,
    }
    assert f"user={support.ALICE.username}" in record.getMessage()


async def test_the_infraenv_namespace_is_passed_when_the_deployment_sets_one(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    inventory: FakeServerInventory,
    workflow: FakeUninstallWorkflow,
) -> None:
    service = nodes_of(
        build(support, gitlab, clock, inventory, workflow, MCE_INFRAENV_NAMESPACE="hw-inventory")
    )
    await service.uninstall(LARK, A.id, server_name=A.name, user=support.ALICE)
    assert workflow.starts[0]["namespace"] == "hw-inventory"


async def test_after_a_start_the_next_read_shows_the_run(nodes: NodeService, support: Any) -> None:
    await nodes.nodes(LARK)  # the run list is now cached
    await nodes.uninstall(LARK, B.id, server_name=B.name, user=support.ALICE)
    shown = {n.server.id: n.uninstall for n in (await nodes.nodes(LARK)).nodes}[B.id]
    assert shown is not None
    assert (shown.status, shown.phase) == ("running", "checking-inventory")


async def test_the_server_is_read_fresh_so_a_moved_node_is_refused(
    nodes: NodeService,
    inventory: FakeServerInventory,
    workflow: FakeUninstallWorkflow,
    support: Any,
) -> None:
    await nodes.nodes(LARK)  # the fleet rows are now cached
    inventory.replace(dataclasses.replace(A, cluster_name=HAWK))
    with pytest.raises(NodeNotInClusterError, match=f"in {HAWK}, not in ocp4-prod-lark-site1"):
        await nodes.uninstall(LARK, A.id, server_name=A.name, user=support.ALICE)
    assert inventory.server_reads == 1
    assert workflow.starts == []


@pytest.mark.parametrize("row", [ELSEWHERE, FREE])
async def test_a_server_server_scan_does_not_place_in_the_cluster_is_refused(
    nodes: NodeService, workflow: FakeUninstallWorkflow, support: Any, row: ServerRow
) -> None:
    with pytest.raises(NodeNotInClusterError):
        await nodes.uninstall(LARK, row.id, server_name=row.name, user=support.ALICE)
    assert workflow.starts == []


async def test_a_name_that_is_not_the_servers_is_refused_and_nothing_starts(
    nodes: NodeService, workflow: FakeUninstallWorkflow, support: Any
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        await nodes.uninstall(LARK, A.id, server_name=B.name, user=support.ALICE)
    assert caught.value.problems == (f"type {A.name} to confirm uninstalling it",)
    assert workflow.starts == []


async def test_a_contested_server_or_one_on_another_mce_is_left_to_the_workflow(
    nodes: NodeService,
    inventory: FakeServerInventory,
    workflow: FakeUninstallWorkflow,
    support: Any,
) -> None:
    inventory.replace(dataclasses.replace(A, contested=True, mce="ocp4-prod-mce-site1-b"))
    await nodes.uninstall(LARK, A.id, server_name=A.name, user=support.ALICE)
    assert workflow.starts == [{"server_name": A.name, "mce": MCE, "namespace": None}]


async def test_an_unknown_server_is_not_found(nodes: NodeService, support: Any) -> None:
    with pytest.raises(ServerNotFoundError):
        await nodes.uninstall(LARK, "srv_nope", server_name="x", user=support.ALICE)


async def test_a_second_start_while_one_runs_is_already_running(
    nodes: NodeService, support: Any
) -> None:
    await nodes.uninstall(LARK, A.id, server_name=A.name, user=support.ALICE)
    with pytest.raises(UninstallAlreadyRunningError):
        await nodes.uninstall(LARK, A.id, server_name=A.name, user=support.BOB)


async def test_an_ambiguous_start_is_surfaced_once_and_logged_with_who(
    nodes: NodeService, workflow: FakeUninstallWorkflow, support: Any, caplog: Any
) -> None:
    workflow.fail_start = AmbiguousStartError("sent, no answer (fake)")
    with pytest.raises(AmbiguousStartError):
        await nodes.uninstall(LARK, A.id, server_name=A.name, user=support.ALICE)
    assert len(workflow.starts) == 1, "never retried"
    (record,) = [r for r in caplog.records if getattr(r, "event", None)]
    assert (record.levelno, record.event, record.user) == (
        logging.WARNING,
        "node_uninstall_unconfirmed",
        support.ALICE.username,
    )


async def test_a_start_the_orchestrator_cannot_take_propagates(
    nodes: NodeService, workflow: FakeUninstallWorkflow, support: Any
) -> None:
    workflow.fail_start = WorkflowsUnavailableError("Temporal refused (fake)")
    with pytest.raises(WorkflowsUnavailableError):
        await nodes.uninstall(LARK, A.id, server_name=A.name, user=support.ALICE)
