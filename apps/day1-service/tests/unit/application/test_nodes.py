"""A cluster's nodes by NodePool and starting an uninstall, on the fakes (ADR-0038).

Built with ``create_app`` on the fake MCE, fleet and orchestrator the
fixtures describe, so the caches main.py puts in front of them are the ones
tested.
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI

from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.application.nodes import (
    ORCHESTRATOR_NOT_CONFIGURED,
    SERVER_SCAN_NOT_CONFIGURED,
    NodeService,
)
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    HubNotConfiguredError,
    HubObjectNotFoundError,
    HubUnavailableError,
    InvalidInputError,
    NodeNotInClusterError,
    ServerNotFoundError,
    ServerScanNotConfiguredError,
    UninstallAlreadyRunningError,
    WorkflowsNotConfiguredError,
)
from wingman_day1.domain.machines import MachineObservation
from wingman_day1.domain.names import HostedClusterNaming
from wingman_day1.domain.node_pools import NodeState
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.servers import ServerRow
from wingman_day1.domain.workflows import WorkflowRun
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import (
    FakeServerInventory,
    FakeUninstallWorkflow,
    default_fleet_file,
    load_fleet,
)
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_mce import default_mce_file, load_fake_mce
from wingman_day1.ports import HubApi, ServerInventory, UninstallWorkflow

SITE1_A = "ocp4-prod-mce-site1-a"
LARK = ClusterRef("site1", SITE1_A, "ocp4-prod-lark-site1")
HERZI = ClusterRef("site1", SITE1_A, "ocp4-prod-herzi-site1")
HAWK = ClusterRef("site1", SITE1_A, "ocp4-prod-hawk-site1")
UI = "https://server-scan.example"
DL0102 = "ocp-dell-r660-site1-128c-1024gb-DLFAKE0102"
DL0105 = "ocp-dell-r760-site1-64c-512gb-DLFAKE0105"
HP0204 = "ocp-hp-gen11-site1-64c-512gb-HPFAKE0204"


class FixedClock:
    def __call__(self) -> datetime:
        return datetime(2026, 11, 11, 8, 0, tzinfo=UTC)


class CountingHub:
    """The fake MCE, counting its Machine reads."""

    def __init__(self, inner: FakeHubApi) -> None:
        self.inner = inner
        self.reads = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    async def machines(self, mce: str, *, namespace: str) -> list[MachineObservation]:
        self.reads += 1
        return await self.inner.machines(mce, namespace=namespace)


def fleet() -> tuple[list[ServerRow], list[WorkflowRun]]:
    return load_fleet(default_fleet_file())


def mce() -> FakeHubApi:
    return load_fake_mce(default_mce_file(), servers=fleet()[0], naming=HostedClusterNaming())


@pytest.fixture
def inventory() -> FakeServerInventory:
    return FakeServerInventory(fleet()[0])


@pytest.fixture
def workflow(inventory: FakeServerInventory) -> FakeUninstallWorkflow:
    return FakeUninstallWorkflow(inventory, clock=FixedClock(), runs=fleet()[1])


@pytest.fixture
def hub() -> FakeHubApi:
    return mce()


def build(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    hub: HubApi | None,
    inventory: ServerInventory | None,
    workflow: UninstallWorkflow | None,
    **settings: object,
) -> FastAPI:
    return support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=None,
        day2=FakeDay2Addons(),
        clock=clock,
        inventory=inventory,
        uninstall=workflow,
        SERVER_SCAN_UI_URL=UI,
        **settings,
    )


def service(app: FastAPI) -> NodeService:
    found = app.state.day1.nodes
    assert isinstance(found, NodeService)
    return found


@pytest.fixture
def nodes(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    hub: FakeHubApi,
    inventory: FakeServerInventory,
    workflow: FakeUninstallWorkflow,
) -> NodeService:
    return service(build(support, gitlab, clock, hub, inventory, workflow))


# ── Listing ──────────────────────────────────────────────────────────────────


async def test_nodes_are_grouped_by_node_pool_with_their_servers_and_links(
    nodes: NodeService,
) -> None:
    found = await nodes.nodes(LARK)
    assert found.hosted_cluster == "ocp4-prod-lark-site1"
    assert [p.name for p in found.node_pools] == [
        "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb",
        "prod-lark-site1-dell-r760-site1-64c-512gb-20tb",
    ]
    rebooting = found.node_pools[0].nodes[0]
    assert (rebooting.state, rebooting.current, rebooting.server_name) == (
        NodeState.NOT_READY,
        True,
        DL0102,
    )
    assert rebooting.server is not None
    assert found.server_urls[rebooting.server.id] == f"{UI}/servers/{rebooting.server.id}"
    assert [row.name for row in found.unassigned] == [DL0105]
    assert found.server_urls[found.unassigned[0].id].startswith(f"{UI}/servers/")
    assert (found.uninstall_available, found.uninstall_detail) == (True, None)
    assert (found.server_scan_error, found.runs_error) == (None, None)


async def test_a_servers_newest_run_is_shown_on_its_node(nodes: NodeService) -> None:
    found = await nodes.nodes(HERZI)
    draining = next(n for n in found.node_pools[0].nodes if n.state is NodeState.DELETING)
    assert draining.server is not None
    run = found.runs[draining.server.id]
    assert (run.status, run.phase) == ("failed", "reserving-server")
    assert run.error is not None and run.error.startswith("ServerReservedError")


async def test_without_server_scan_nodes_list_by_their_hosts_and_uninstall_is_off(
    support: Any, gitlab: InMemoryGitLab, clock: Any, hub: FakeHubApi
) -> None:
    found = await service(build(support, gitlab, clock, hub, None, None)).nodes(LARK)
    node = found.node_pools[0].nodes[0]
    assert (node.server, node.server_name) == (None, DL0102.lower())
    assert found.unassigned == ()
    assert (found.uninstall_available, found.uninstall_detail) == (
        False,
        ORCHESTRATOR_NOT_CONFIGURED,
    )
    assert found.server_scan_error is None


async def test_without_server_scan_but_with_an_orchestrator_uninstall_is_off_for_server_scan(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    hub: FakeHubApi,
    workflow: FakeUninstallWorkflow,
) -> None:
    found = await service(build(support, gitlab, clock, hub, None, workflow)).nodes(LARK)
    assert (found.uninstall_available, found.uninstall_detail) == (
        False,
        SERVER_SCAN_NOT_CONFIGURED,
    )


async def test_an_unreadable_server_scan_leaves_the_nodes_and_says_why(
    nodes: NodeService, inventory: FakeServerInventory
) -> None:
    inventory.unavailable = True
    found = await nodes.nodes(LARK)
    assert sum(len(p.nodes) for p in found.node_pools) == 5
    assert all(n.server is None for p in found.node_pools for n in p.nodes)
    assert found.unassigned == ()
    assert found.server_scan_error == "ServerScanUnavailable: server-scan unreachable (fake)"


async def test_an_unreadable_orchestrator_leaves_the_nodes_and_says_runs_are_unknown(
    nodes: NodeService, workflow: FakeUninstallWorkflow
) -> None:
    workflow.unavailable = True
    found = await nodes.nodes(HERZI)
    assert found.runs == {}
    assert found.runs_error == "WorkflowsUnavailable: the orchestrator is unreachable (fake)"
    assert found.uninstall_available


@pytest.mark.parametrize(
    ("hub", "error"),
    [
        (FakeHubApi(mces=["ocp4-prod-mce-site2-a"]), HubNotConfiguredError),
        (FakeHubApi(mces=[SITE1_A]), HubObjectNotFoundError),
        (FakeHubApi(unavailable=[SITE1_A]), HubUnavailableError),
    ],
)
async def test_an_mce_that_cannot_tell_fails_the_read(
    support: Any, gitlab: InMemoryGitLab, clock: Any, hub: FakeHubApi, error: type[Exception]
) -> None:
    """No token for the MCE, no HostedCluster on it (not applied yet), or no answer."""
    with pytest.raises(error):
        await service(build(support, gitlab, clock, hub, None, None)).nodes(LARK)


async def test_the_mce_reads_are_cached_briefly(
    support: Any, gitlab: InMemoryGitLab, clock: Any, inventory: FakeServerInventory
) -> None:
    counting = CountingHub(mce())
    nodes = service(build(support, gitlab, clock, counting, inventory, None))  # ty: ignore[invalid-argument-type]
    await nodes.nodes(LARK)
    await nodes.nodes(LARK)
    assert counting.reads == 1


async def test_a_hosted_cluster_without_an_agent_namespace_cannot_count_free_agents(
    support: Any, gitlab: InMemoryGitLab, clock: Any, hub: FakeHubApi
) -> None:
    key = (SITE1_A, "hcp-prod-lark-site1", "ocp4-prod-lark-site1")
    hub._hosted_clusters[key] = dataclasses.replace(hub._hosted_clusters[key], agent_namespace=None)
    found = await service(build(support, gitlab, clock, hub, None, None)).nodes(LARK)
    assert {p.free_agents for p in found.node_pools} == {None}
    waiting = found.node_pools[1].nodes[0]
    assert waiting.waiting_for is not None and "could not be counted" in waiting.waiting_for


# ── Uninstall ────────────────────────────────────────────────────────────────


async def test_an_uninstall_starts_the_workflow_on_the_clusters_mce_and_logs_who(
    nodes: NodeService, workflow: FakeUninstallWorkflow, support: Any, caplog: Any
) -> None:
    caplog.set_level(logging.INFO, logger="wingman_day1.application.nodes")
    run = await nodes.uninstall(
        LARK, "srv_00000000000000000000000000000102", server_name=DL0102.lower(), user=support.ALICE
    )
    workflow_id = f"uninstall-server-from-hc-{DL0102.lower()}"
    assert run == WorkflowRun(workflow_id, "running")
    assert workflow.starts == [{"server_name": DL0102, "mce": SITE1_A, "namespace": None}]
    (record,) = [r for r in caplog.records if getattr(r, "event", None)]
    assert {
        key: getattr(record, key)
        for key in ("event", "user", "cluster", "mce", "server_name", "workflow_id")
    } == {
        "event": "node_uninstall_started",
        "user": support.ALICE.username,
        "cluster": LARK.name,
        "mce": SITE1_A,
        "server_name": DL0102,
        "workflow_id": workflow_id,
    }


async def test_a_server_only_a_machine_leads_to_can_be_uninstalled(
    nodes: NodeService, workflow: FakeUninstallWorkflow, support: Any
) -> None:
    # HPFAKE0204 is installing into herzi: server-scan has no cluster for it yet.
    await nodes.uninstall(
        HERZI, "srv_00000000000000000000000000000204", server_name=HP0204, user=support.ALICE
    )
    assert workflow.starts[0]["server_name"] == HP0204


async def test_a_server_only_server_scan_places_in_the_cluster_can_be_uninstalled(
    nodes: NodeService, workflow: FakeUninstallWorkflow, support: Any
) -> None:
    await nodes.uninstall(
        LARK, "srv_00000000000000000000000000000105", server_name=DL0105, user=support.ALICE
    )
    assert workflow.starts[0]["server_name"] == DL0105


async def test_a_server_neither_places_in_the_cluster_is_refused(
    nodes: NodeService,
    workflow: FakeUninstallWorkflow,
    inventory: FakeServerInventory,
    support: Any,
) -> None:
    with pytest.raises(NodeNotInClusterError, match="no Machine of ocp4-prod-hawk-site1 leads to"):
        await nodes.uninstall(
            HAWK, "srv_00000000000000000000000000000102", server_name=DL0102, user=support.ALICE
        )
    assert workflow.starts == []
    assert inventory.server_reads == 1, "the server is read fresh"


async def test_a_name_that_is_not_the_servers_is_refused_and_nothing_starts(
    nodes: NodeService, workflow: FakeUninstallWorkflow, support: Any
) -> None:
    with pytest.raises(InvalidInputError) as caught:
        await nodes.uninstall(
            LARK, "srv_00000000000000000000000000000102", server_name=DL0105, user=support.ALICE
        )
    assert caught.value.problems == (f"type {DL0102} to confirm uninstalling it",)
    assert workflow.starts == []


async def test_an_unknown_server_is_not_found(nodes: NodeService, support: Any) -> None:
    with pytest.raises(ServerNotFoundError):
        await nodes.uninstall(LARK, "srv_nope", server_name="x", user=support.ALICE)


@pytest.mark.parametrize(
    ("with_inventory", "with_workflow", "error"),
    [(True, False, WorkflowsNotConfiguredError), (False, True, ServerScanNotConfiguredError)],
)
async def test_an_uninstall_needs_server_scan_and_the_orchestrator(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    hub: FakeHubApi,
    inventory: FakeServerInventory,
    workflow: FakeUninstallWorkflow,
    with_inventory: bool,
    with_workflow: bool,
    error: type[Exception],
) -> None:
    app = build(
        support,
        gitlab,
        clock,
        hub,
        inventory if with_inventory else None,
        workflow if with_workflow else None,
    )
    with pytest.raises(error):
        await service(app).uninstall(LARK, "srv_x", server_name="x", user=support.ALICE)


async def test_the_infraenv_namespace_is_passed_when_the_deployment_sets_one(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    hub: FakeHubApi,
    inventory: FakeServerInventory,
    workflow: FakeUninstallWorkflow,
) -> None:
    app = build(
        support, gitlab, clock, hub, inventory, workflow, MCE_INFRAENV_NAMESPACE="hw-inventory"
    )
    await service(app).uninstall(
        LARK, "srv_00000000000000000000000000000102", server_name=DL0102, user=support.ALICE
    )
    assert workflow.starts[0]["namespace"] == "hw-inventory"


async def test_a_second_start_while_one_runs_is_already_running(
    nodes: NodeService, support: Any
) -> None:
    sid = "srv_00000000000000000000000000000102"
    await nodes.uninstall(LARK, sid, server_name=DL0102, user=support.ALICE)
    with pytest.raises(UninstallAlreadyRunningError):
        await nodes.uninstall(LARK, sid, server_name=DL0102, user=support.BOB)


async def test_after_a_start_the_next_read_shows_the_run(nodes: NodeService, support: Any) -> None:
    sid = "srv_00000000000000000000000000000102"
    await nodes.nodes(LARK)  # the run list is now cached
    await nodes.uninstall(LARK, sid, server_name=DL0102, user=support.ALICE)
    run = (await nodes.nodes(LARK)).runs[sid]
    assert (run.status, run.phase) == ("running", "checking-inventory")


async def test_an_ambiguous_start_is_surfaced_once_and_logged_with_who(
    nodes: NodeService, workflow: FakeUninstallWorkflow, support: Any, caplog: Any
) -> None:
    workflow.fail_start = AmbiguousStartError("sent, no answer (fake)")
    with pytest.raises(AmbiguousStartError):
        await nodes.uninstall(
            LARK, "srv_00000000000000000000000000000102", server_name=DL0102, user=support.ALICE
        )
    assert len(workflow.starts) == 1, "never retried"
    (record,) = [r for r in caplog.records if getattr(r, "event", None)]
    assert (record.levelno, record.__dict__["event"]) == (
        logging.WARNING,
        "node_uninstall_unconfirmed",
    )
