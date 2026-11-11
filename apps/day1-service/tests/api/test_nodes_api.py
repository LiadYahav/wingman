"""The cluster nodes routes, as docs/notes/2026-11-11-cluster-nodes-api.md fixes them (ADR-0038)."""

from __future__ import annotations

import dataclasses
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
from wingman_day1.domain.servers import ServerRow
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory, FakeUninstallWorkflow

Auth = Callable[[User], dict[str, str]]
MCE = "ocp4-prod-mce-site1-a"
LARK = "ocp4-prod-lark-site1"
NODES = f"/api/day1/clusters/{LARK}/nodes"
NODE = ServerRow(
    id="srv_0d48131a4fcc4b4c9cc8eec6ef72c421",
    name="ocp-dell-r660-site1-64c-512gb-DL0000123",
    state="INSTALLED",
    health="HEALTHY",
    serial="DL0000123",
    vendor="dell",
    model="PowerEdge R660",
    site="site1",
    cluster_name=LARK,
    mce=MCE,
    last_seen_at=datetime(2026, 11, 11, 8, 0, 3, tzinfo=UTC),
)
OTHER = dataclasses.replace(
    NODE, id="srv_other", name="ocp-dell-r660-site1-64c-512gb-DL0000999", cluster_name="x"
)
UNINSTALL = f"{NODES}/{NODE.id}/uninstall"
WORKFLOW_ID = "uninstall-server-from-hc-ocp-dell-r660-site1-64c-512gb-dl0000123"


class FixedClock:
    def __call__(self) -> datetime:
        return datetime(2026, 11, 11, 8, 0, tzinfo=UTC)


@pytest.fixture
def inventory() -> FakeServerInventory:
    return FakeServerInventory([NODE, OTHER])


@pytest.fixture
def workflow(inventory: FakeServerInventory) -> FakeUninstallWorkflow:
    return FakeUninstallWorkflow(inventory, clock=FixedClock())


async def serve(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        yield client


def fleet_app(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    inventory: FakeServerInventory,
    workflow: FakeUninstallWorkflow | None,
) -> FastAPI:
    return support.build_app(
        gitlab=gitlab,
        hub=None,
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
    inventory: FakeServerInventory,
    workflow: FakeUninstallWorkflow,
) -> AsyncIterator[httpx.AsyncClient]:
    async for client in serve(fleet_app(support, gitlab, clock, inventory, workflow)):
        yield client


@pytest.fixture
async def no_orchestrator(
    support: Any, gitlab: InMemoryGitLab, clock: Any, inventory: FakeServerInventory
) -> AsyncIterator[httpx.AsyncClient]:
    async for client in serve(fleet_app(support, gitlab, clock, inventory, None)):
        yield client


async def uninstall(
    client: httpx.AsyncClient,
    auth: Auth,
    user: User,
    *,
    name: str = NODE.name,
    path: str = UNINSTALL,
) -> httpx.Response:
    return await client.post(path, json={"server_name": name}, headers=auth(user))


# ── Off ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("method", "body"), [("GET", None), ("POST", {"server_name": "x"})])
async def test_both_routes_answer_501_when_server_scan_is_not_configured(
    client: httpx.AsyncClient, auth: Auth, support: Any, method: str, body: object
) -> None:
    path = NODES if method == "GET" else UNINSTALL
    response = await client.request(method, path, json=body, headers=auth(support.ALICE))
    problem = response.json()
    assert (response.status_code, problem["code"]) == (501, "FEATURE_DISABLED")
    assert "SERVER_SCAN_URL" in problem["detail"]


async def test_without_an_orchestrator_nodes_are_listed_and_the_start_answers_501(
    no_orchestrator: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    listed = await no_orchestrator.get(NODES, headers=auth(support.VIEWER))
    assert listed.status_code == 200
    body = listed.json()
    assert body["uninstall"]["available"] is False
    assert "WORKFLOWS_API_URL" in body["uninstall"]["detail"]
    assert body["runs_error"] is None
    started = await uninstall(no_orchestrator, auth, support.ALICE)
    assert (started.status_code, started.json()["code"]) == (501, "FEATURE_DISABLED")


# ── Reading ──────────────────────────────────────────────────────────────────


async def test_the_nodes_answer_has_exactly_the_contracts_shape(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await fleet.get(
        NODES, params={"site": "site1", "mce": MCE}, headers=auth(support.VIEWER)
    )
    assert response.status_code == 200
    assert response.json() == {
        "hosted_cluster": LARK,
        "nodes": [
            {
                "id": NODE.id,
                "name": NODE.name,
                "url": f"https://server-scan.example/servers/{NODE.id}",
                "serial": "DL0000123",
                "vendor": "dell",
                "model": "PowerEdge R660",
                "site": "site1",
                "mce": MCE,
                "state": "INSTALLED",
                "health": "HEALTHY",
                "maintenance": False,
                "reachable": True,
                "stale": False,
                "contested": False,
                "last_seen_at": "2026-11-11T08:00:03+00:00",
                "uninstall": None,
            }
        ],
        "uninstall": {"available": True, "detail": None},
        "runs_error": None,
    }


async def test_a_node_shows_its_run_once_one_started(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    await uninstall(fleet, auth, support.ALICE)
    node = (await fleet.get(NODES, headers=auth(support.VIEWER))).json()["nodes"][0]
    assert node["uninstall"] == {
        "workflow_id": WORKFLOW_ID,
        "status": "running",
        "phase": "checking-inventory",
        "error": None,
    }


async def test_an_unreadable_orchestrator_still_lists_the_nodes(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeUninstallWorkflow
) -> None:
    workflow.unavailable = True
    response = await fleet.get(NODES, headers=auth(support.VIEWER))
    assert response.status_code == 200
    body = response.json()
    assert [n["uninstall"] for n in body["nodes"]] == [None]
    assert body["runs_error"].startswith("WorkflowsUnavailable:")


async def test_server_scan_down_is_a_502_not_an_empty_list(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, inventory: FakeServerInventory
) -> None:
    inventory.unavailable = True
    response = await fleet.get(NODES, headers=auth(support.VIEWER))
    assert (response.status_code, response.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")


async def test_an_unknown_cluster_is_not_found_on_both_routes(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    path = "/api/day1/clusters/ocp4-prod-nope-site1/nodes"
    assert (await fleet.get(path, headers=auth(support.VIEWER))).status_code == 404
    started = await uninstall(fleet, auth, support.ALICE, path=f"{path}/{NODE.id}/uninstall")
    assert (started.status_code, started.json()["code"]) == (404, "NOT_FOUND")


async def test_reading_nodes_needs_a_session(fleet: httpx.AsyncClient) -> None:
    assert (await fleet.get(NODES)).status_code == 401


# ── Uninstall ────────────────────────────────────────────────────────────────


async def test_an_admin_starts_an_uninstall_and_gets_the_run(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeUninstallWorkflow
) -> None:
    response = await uninstall(fleet, auth, support.ALICE, name=NODE.name.upper())
    assert (response.status_code, response.json()) == (
        202,
        {"workflow_id": WORKFLOW_ID, "status": "running", "phase": None, "error": None},
    )
    assert workflow.starts == [{"server_name": NODE.name, "mce": MCE, "namespace": None}]


async def test_a_viewer_cannot_start_one(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeUninstallWorkflow
) -> None:
    response = await uninstall(fleet, auth, support.VIEWER)
    assert (response.status_code, response.json()["code"]) == (403, "FORBIDDEN")
    assert workflow.starts == []


async def test_a_name_that_is_not_the_servers_is_422_and_nothing_starts(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeUninstallWorkflow
) -> None:
    response = await uninstall(fleet, auth, support.ALICE, name=OTHER.name)
    problem = response.json()
    assert (response.status_code, problem["code"]) == (422, "VALIDATION_ERROR")
    assert problem["details"]["problems"] == [f"type {NODE.name} to confirm uninstalling it"]
    assert workflow.starts == []


@pytest.mark.parametrize(
    "body", [{}, {"server_name": ""}, {"server_name": NODE.name, "force": True}]
)
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
    response = await uninstall(fleet, auth, support.ALICE, path=f"{NODES}/srv%20x/uninstall")
    assert response.status_code == 422


async def test_an_unknown_server_is_404(fleet: httpx.AsyncClient, auth: Auth, support: Any) -> None:
    response = await uninstall(fleet, auth, support.ALICE, path=f"{NODES}/srv_nope/uninstall")
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")


async def test_a_server_in_another_cluster_is_node_not_in_cluster(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeUninstallWorkflow
) -> None:
    path = f"{NODES}/{OTHER.id}/uninstall"
    response = await uninstall(fleet, auth, support.ALICE, name=OTHER.name, path=path)
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
