"""The cluster nodes routes, as docs/notes/2026-11-11-cluster-nodes-api.md fixes them (ADR-0038)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    WorkflowsError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.names import HostedClusterNaming
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import (
    FakeServerInventory,
    FakeUninstallWorkflow,
    default_fleet_file,
    load_fleet,
)
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_mce import default_mce_file, load_fake_mce

Auth = Callable[[User], dict[str, str]]
SITE1_A = "ocp4-prod-mce-site1-a"
LARK = "ocp4-prod-lark-site1"
NODES = f"/api/day1/clusters/{LARK}/nodes"
DL0102 = "ocp-dell-r660-site1-128c-1024gb-DLFAKE0102"
SRV0102 = "srv_00000000000000000000000000000102"
UNINSTALL = f"{NODES}/{SRV0102}/uninstall"
WORKFLOW_ID = f"uninstall-server-from-hc-{DL0102.lower()}"
TOP = {"hosted_cluster", "node_pools", "unassigned", "uninstall", "server_scan_error", "runs_error"}
POOL = {
    "name",
    "wanted",
    "autoscaling",
    "ready",
    "version",
    "upgrade_type",
    "agent_selector",
    "update",
    "problems",
    "free_agents",
    "nodes",
}
NODE = {
    "machine",
    "node_name",
    "state",
    "current",
    "activity",
    "waiting_for",
    "outdated",
    "agent",
    "server_name",
    "server",
    "uninstall",
}
SERVER = {
    "id",
    "name",
    "url",
    "serial",
    "vendor",
    "model",
    "site",
    "mce",
    "state",
    "health",
    "maintenance",
    "reachable",
    "stale",
    "contested",
    "last_seen_at",
}


class FixedClock:
    def __call__(self) -> datetime:
        return datetime(2026, 11, 11, 8, 0, tzinfo=UTC)


@pytest.fixture
def inventory() -> FakeServerInventory:
    return FakeServerInventory(load_fleet(default_fleet_file())[0])


@pytest.fixture
def workflow(inventory: FakeServerInventory) -> FakeUninstallWorkflow:
    return FakeUninstallWorkflow(
        inventory, clock=FixedClock(), runs=load_fleet(default_fleet_file())[1]
    )


@pytest.fixture
def mce() -> FakeHubApi:
    rows = load_fleet(default_fleet_file())[0]
    return load_fake_mce(default_mce_file(), servers=rows, naming=HostedClusterNaming())


async def serve(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        yield client


def app_of(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    hub: FakeHubApi | None,
    inventory: FakeServerInventory | None = None,
    workflow: FakeUninstallWorkflow | None = None,
) -> FastAPI:
    return support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=None,
        day2=FakeDay2Addons(),
        clock=clock,
        inventory=inventory,
        uninstall=workflow,
        SERVER_SCAN_URL="http://server-scan-api.inventory.svc:8000",
        SERVER_SCAN_UI_URL="https://server-scan.example",
    )


@pytest.fixture
async def fleet(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    mce: FakeHubApi,
    inventory: FakeServerInventory,
    workflow: FakeUninstallWorkflow,
) -> AsyncIterator[httpx.AsyncClient]:
    async for client in serve(app_of(support, gitlab, clock, mce, inventory, workflow)):
        yield client


async def uninstall(
    client: httpx.AsyncClient, auth: Auth, user: User, *, name: str = DL0102, path: str = UNINSTALL
) -> httpx.Response:
    return await client.post(path, json={"server_name": name}, headers=auth(user))


# ── Off ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("method", "body"), [("GET", None), ("POST", {"server_name": "x"})])
async def test_both_routes_answer_501_without_live_status(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    auth: Auth,
    inventory: FakeServerInventory,
    method: str,
    body: object,
) -> None:
    async for client in serve(app_of(support, gitlab, clock, None, inventory)):
        path = NODES if method == "GET" else UNINSTALL
        response = await client.request(method, path, json=body, headers=auth(support.ALICE))
        problem = response.json()
        assert (response.status_code, problem["code"]) == (501, "FEATURE_DISABLED")
        assert "CLUSTER_STATUS_ENABLED" in problem["detail"]


@pytest.mark.parametrize(
    ("with_inventory", "named"), [(False, "SERVER_SCAN_URL"), (True, "WORKFLOWS_API_URL")]
)
async def test_without_server_scan_or_the_orchestrator_nodes_list_and_the_start_answers_501(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    auth: Auth,
    mce: FakeHubApi,
    inventory: FakeServerInventory,
    with_inventory: bool,
    named: str,
) -> None:
    workflow = None if with_inventory else FakeUninstallWorkflow(inventory, clock=FixedClock())
    app = app_of(support, gitlab, clock, mce, inventory if with_inventory else None, workflow)
    async for client in serve(app):
        listed = await client.get(NODES, headers=auth(support.VIEWER))
        assert listed.status_code == 200
        assert listed.json()["uninstall"]["available"] is False
        assert named in listed.json()["uninstall"]["detail"]
        started = await uninstall(client, auth, support.ALICE)
        assert (started.status_code, started.json()["code"]) == (501, "FEATURE_DISABLED")
        assert named in started.json()["detail"]


# ── Reading ──────────────────────────────────────────────────────────────────


async def test_the_nodes_answer_has_exactly_the_contracts_shape(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await fleet.get(
        NODES, params={"site": "site1", "mce": SITE1_A}, headers=auth(support.VIEWER)
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == TOP
    assert (body["hosted_cluster"], body["server_scan_error"], body["runs_error"]) == (
        LARK,
        None,
        None,
    )
    assert body["uninstall"] == {"available": True, "detail": None}
    in_place, replace = body["node_pools"]
    assert set(in_place) == POOL
    assert {key: in_place[key] for key in POOL - {"nodes", "problems"}} == {
        "name": "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb",
        "wanted": 3,
        "autoscaling": None,
        "ready": 2,
        "version": "4.18.22",
        "upgrade_type": "InPlace",
        "agent_selector": "infraenvs.agent-install.openshift.io=dell-r660-site1-128c-1024gb-5tb",
        "update": {
            "kind": "version",
            "message": in_place["update"]["message"],
            "progress": {"total": 3, "updated": 1},
            "failed": False,
        },
        "free_agents": {"matching": 3, "free": 0},
    }
    assert in_place["update"]["message"].startswith("Nodepool update in progress.")
    assert in_place["problems"][0].startswith("AllNodesHealthy: NodeConditionsFailed: 1 of 3")
    rebooting = in_place["nodes"][0]
    assert set(rebooting) == NODE
    assert set(rebooting["server"]) == SERVER
    assert {k: rebooting[k] for k in NODE - {"machine", "agent", "server"}} == {
        "node_name": DL0102.lower(),
        "state": "not_ready",
        "current": True,
        "activity": "Rebooting for the update (Node condition Ready is Unknown)",
        "waiting_for": None,
        "outdated": None,
        "server_name": DL0102,
        "uninstall": None,
    }
    assert rebooting["machine"].startswith("prod-lark-site1-dell-r660-site1-128c-1024gb-5tb-")
    assert set(rebooting["agent"]) == {"name", "state", "stage"}
    assert rebooting["server"]["url"] == f"https://server-scan.example/servers/{SRV0102}"
    assert rebooting["server"]["last_seen_at"] == "2026-11-11T08:00:03+00:00"
    waiting = replace["nodes"][0]
    assert (waiting["state"], waiting["server"], waiting["agent"]) == ("waiting", None, None)
    assert "(2 bound, 1 not approved)" in waiting["waiting_for"]
    (left,) = body["unassigned"]
    assert set(left) == SERVER | {"uninstall"}
    assert left["name"] == "ocp-dell-r760-site1-64c-512gb-DLFAKE0105"


async def test_a_nodes_run_is_shown_once_one_started(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    await uninstall(fleet, auth, support.ALICE)
    node = (await fleet.get(NODES, headers=auth(support.VIEWER))).json()["node_pools"][0]["nodes"][
        0
    ]
    assert node["uninstall"] == {
        "workflow_id": WORKFLOW_ID,
        "status": "running",
        "phase": "checking-inventory",
        "error": None,
    }


async def test_server_scan_or_the_orchestrator_unreadable_still_lists_the_nodes(
    fleet: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    inventory: FakeServerInventory,
    workflow: FakeUninstallWorkflow,
) -> None:
    inventory.unavailable = True
    workflow.unavailable = True
    response = await fleet.get(NODES, headers=auth(support.VIEWER))
    assert response.status_code == 200
    body = response.json()
    assert body["server_scan_error"].startswith("ServerScanUnavailable:")
    assert body["unassigned"] == []
    assert body["node_pools"][0]["nodes"][0]["server"] is None


@pytest.mark.parametrize(
    ("hub", "status", "code"),
    [
        (FakeHubApi(unavailable=[SITE1_A]), 502, "DEPENDENCY_UNAVAILABLE"),
        (FakeHubApi(mces=[SITE1_A]), 404, "NOT_FOUND"),
        (FakeHubApi(mces=["ocp4-prod-mce-site2-a"]), 422, "VALIDATION_ERROR"),
    ],
)
async def test_an_mce_that_cannot_tell_answers_its_problem(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    auth: Auth,
    hub: FakeHubApi,
    status: int,
    code: str,
) -> None:
    async for client in serve(app_of(support, gitlab, clock, hub)):
        response = await client.get(NODES, headers=auth(support.VIEWER))
        assert (response.status_code, response.json()["code"]) == (status, code)


async def test_an_unknown_cluster_is_not_found_on_both_routes(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    path = "/api/day1/clusters/ocp4-prod-nope-site1/nodes"
    assert (await fleet.get(path, headers=auth(support.VIEWER))).status_code == 404
    started = await uninstall(fleet, auth, support.ALICE, path=f"{path}/{SRV0102}/uninstall")
    assert (started.status_code, started.json()["code"]) == (404, "NOT_FOUND")


async def test_reading_nodes_needs_a_session(fleet: httpx.AsyncClient) -> None:
    assert (await fleet.get(NODES)).status_code == 401


# ── Uninstall ────────────────────────────────────────────────────────────────


async def test_an_admin_starts_an_uninstall_and_gets_the_run(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeUninstallWorkflow
) -> None:
    response = await uninstall(fleet, auth, support.ALICE, name=DL0102.upper())
    assert (response.status_code, response.json()) == (
        202,
        {"workflow_id": WORKFLOW_ID, "status": "running", "phase": None, "error": None},
    )
    assert workflow.starts == [{"server_name": DL0102, "mce": SITE1_A, "namespace": None}]


async def test_a_viewer_cannot_start_one(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeUninstallWorkflow
) -> None:
    response = await uninstall(fleet, auth, support.VIEWER)
    assert (response.status_code, response.json()["code"]) == (403, "FORBIDDEN")
    assert workflow.starts == []


async def test_a_name_that_is_not_the_servers_is_422_and_nothing_starts(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeUninstallWorkflow
) -> None:
    response = await uninstall(fleet, auth, support.ALICE, name="ocp-something-else")
    problem = response.json()
    assert (response.status_code, problem["code"]) == (422, "VALIDATION_ERROR")
    assert problem["details"]["problems"] == [f"type {DL0102} to confirm uninstalling it"]
    assert workflow.starts == []


@pytest.mark.parametrize("body", [{}, {"server_name": ""}, {"server_name": DL0102, "force": True}])
async def test_the_body_is_only_the_typed_name(
    fleet: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    workflow: FakeUninstallWorkflow,
    body: dict[str, Any],
) -> None:
    response = await fleet.post(UNINSTALL, json=body, headers=auth(support.ALICE))
    assert response.status_code == 422
    assert workflow.starts == []


async def test_a_server_id_that_cannot_be_one_is_422(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    assert (
        await uninstall(fleet, auth, support.ALICE, path=f"{NODES}/srv%20x/uninstall")
    ).status_code == 422


async def test_an_unknown_server_is_404(fleet: httpx.AsyncClient, auth: Auth, support: Any) -> None:
    response = await uninstall(fleet, auth, support.ALICE, path=f"{NODES}/srv_nope/uninstall")
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")


async def test_a_server_neither_a_machine_nor_server_scan_places_here_is_node_not_in_cluster(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeUninstallWorkflow
) -> None:
    path = f"/api/day1/clusters/ocp4-prod-hawk-site1/nodes/{SRV0102}/uninstall"
    response = await uninstall(fleet, auth, support.ALICE, path=path)
    assert (response.status_code, response.json()["code"]) == (409, "NODE_NOT_IN_CLUSTER")
    assert workflow.starts == []


async def test_a_second_start_while_one_runs_is_uninstall_already_running(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    assert (await uninstall(fleet, auth, support.ALICE)).status_code == 202
    again = await uninstall(fleet, auth, support.BOB)
    assert (again.status_code, again.json()["code"]) == (409, "UNINSTALL_ALREADY_RUNNING")


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (WorkflowsUnavailableError("Temporal refused (fake)"), 502, "DEPENDENCY_UNAVAILABLE"),
        (AmbiguousStartError("sent, no answer: look first (fake)"), 504, "AMBIGUOUS_WRITE"),
    ],
)
async def test_a_start_that_failed_or_was_lost_says_which(
    fleet: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    workflow: FakeUninstallWorkflow,
    failure: WorkflowsError,
    status: int,
    code: str,
) -> None:
    workflow.fail_start = failure
    response = await uninstall(fleet, auth, support.ALICE)
    assert (response.status_code, response.json()["code"]) == (status, code)
    assert response.json()["detail"] == str(failure)
    assert len(workflow.starts) == 1


async def test_server_scan_down_refuses_the_start(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, inventory: FakeServerInventory
) -> None:
    inventory.unavailable = True
    response = await uninstall(fleet, auth, support.ALICE)
    assert (response.status_code, response.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
