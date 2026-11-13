"""Inventory Management's routes, as docs/notes/2026-11-13-inventory-management-api.md says."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import (
    AddServerAlreadyRunningError,
    AddServerRefusedError,
    AmbiguousStartError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.names import HostedClusterNaming
from wingman_day1.infrastructure.fake_add_server import FakeAddServerWorkflow
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import (
    FakeServerInventory,
    default_fleet_file,
    load_fleet,
)
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_inventory_demo import (
    default_inventory_file,
    load_inventory_demo,
)
from wingman_day1.infrastructure.fake_mce import default_mce_file, load_fake_mce

Auth = Callable[[User], dict[str, str]]
SITE1_A = "ocp4-prod-mce-site1-a"
R650 = "dell-r650-site1-96c-768gb"
POOL = f"/api/day1/inventory/mces/{SITE1_A}/infra-envs/{R650}"
FREE = "ocp-dell-r650-site1-96c-768gb-DLFAKE0811"
LOCKED = "ocp-dell-r650-site1-96c-768gb-DLFAKE0812"
DONOR = "ocp-dell-r650-site1-96c-768gb-DLFAKE0813"
URLS = {
    "SERVER_SCAN_URL": "http://server-scan-api.inventory.svc:8000",
    "WORKFLOWS_API_URL": "http://workflows-orchestrator-api.redbull-workflows.svc:8080",
}


class FixedClock:
    def __call__(self) -> datetime:
        return datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def inventory() -> FakeServerInventory:
    rows = load_fleet(default_fleet_file())[0]
    demo = load_inventory_demo(default_inventory_file(), now=FixedClock()())
    return FakeServerInventory([*rows, *demo.rows])


@pytest.fixture
def workflow(inventory: FakeServerInventory) -> FakeAddServerWorkflow:
    return FakeAddServerWorkflow(inventory, clock=FixedClock())


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
    *,
    hub: FakeHubApi | None,
    inventory: FakeServerInventory | None,
    workflow: FakeAddServerWorkflow | None,
    **settings: object,
) -> FastAPI:
    return support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=None,
        day2=FakeDay2Addons(),
        clock=clock,
        inventory=inventory,
        add_server=workflow,
        **({"SERVER_SCAN_URL": URLS["SERVER_SCAN_URL"]} if inventory else {}),
        **({"WORKFLOWS_API_URL": URLS["WORKFLOWS_API_URL"]} if workflow else {}),
        **settings,
    )


@pytest.fixture
async def fleet(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    mce: FakeHubApi,
    inventory: FakeServerInventory,
    workflow: FakeAddServerWorkflow,
) -> AsyncIterator[httpx.AsyncClient]:
    app = app_of(
        support, gitlab, clock, hub=mce, inventory=inventory, workflow=workflow,
        DAY1_ADD_SERVERS=True,
    )  # fmt: skip
    async for client in serve(app):
        yield client


# ── Reads ────────────────────────────────────────────────────────────────────


async def test_every_mce_is_counted_by_pool_as_server_scan_reports_it(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await fleet.get("/api/day1/inventory", headers=auth(support.ALICE))
    assert response.status_code == 200
    body = response.json()
    assert body["add_servers"] == {"available": True, "detail": None}
    assert body["runs"] == {"available": True, "detail": None}
    site1_a = next(m for m in body["mces"] if m["mce"] == SITE1_A)
    assert (site1_a["site"], site1_a["known"]) == ("site1", True)
    assert (site1_a["servers"], site1_a["in_clusters"], site1_a["available"]) == (16, 10, 6)
    pools = {p["infra_env"]: p for p in site1_a["pools"]}
    assert pools[R650] == {
        "infra_env": R650,
        "available": 2,
        "usable": 2,
        "hardware": [{"vendor": "dell", "model": "PowerEdge R650", "available": 2, "usable": 2}],
        "drawable": 1,
    }
    assert pools["dell-r760-site1-64c-512gb-20tb"]["drawable"] == 3, "herzi's pool can grow"
    assert pools[None]["available"] == 1, "a name that matches no InfraEnv is not guessed"
    unknown = next(m for m in body["mces"] if m["mce"] == "ocp4-prod-mce-site1-c")
    assert unknown["known"] is False


async def test_a_pools_candidates_show_the_lock_and_offer_no_locked_server(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await fleet.get(f"{POOL}/candidates", headers=auth(support.ALICE))
    assert response.status_code == 200
    found = {c["name"]: c for c in response.json()["candidates"]}
    assert found[FREE]["offered"] is True
    assert found[LOCKED]["offered"] is False
    assert found[LOCKED]["lock"] == {
        "holder": "add-server-to-mce",
        "mce": "ocp4-prod-mce-site1-b",
        "infra_env": R650,
        "expires_at": "2026-11-13T18:00:00+00:00",
    }
    assert found[DONOR]["why_not"] == "in maintenance"
    assert set(found[FREE]) == {
        "id", "name", "vendor", "model", "health", "lock", "offered", "why_not",
    }  # fmt: skip


async def test_an_unknown_mce_or_infra_env_is_not_found(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    for path in (
        "/api/day1/inventory/mces/ocp4-nope/infra-envs/x/candidates",
        f"/api/day1/inventory/mces/{SITE1_A}/infra-envs/nope/candidates",
    ):
        response = await fleet.get(path, headers=auth(support.ALICE))
        assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")


async def test_the_runs_say_who_may_have_started_them(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    await fleet.post(f"{POOL}/add-servers", json={"count": 1}, headers=auth(support.ALICE))
    await fleet.post(
        f"{POOL}/add-servers", json={"server_names": [FREE]}, headers=auth(support.ALICE)
    )
    response = await fleet.get("/api/day1/inventory/runs", headers=auth(support.ALICE))
    assert response.status_code == 200
    named, pool = response.json()["runs"]
    assert (named["origin"], named["server_name"], named["slot"]) == ("named", FREE, None)
    assert (pool["origin"], pool["infra_env"], pool["slot"]) == ("pool", R650, 1)
    assert (pool["mce"], pool["status"], pool["phase"]) == (
        SITE1_A,
        "running",
        "validating-infraenv",
    )


# ── Starting ─────────────────────────────────────────────────────────────────


async def test_a_start_by_count_is_202_and_sent_once(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeAddServerWorkflow
) -> None:
    response = await fleet.post(
        f"{POOL}/add-servers", json={"count": 2}, headers=auth(support.ALICE)
    )
    assert response.status_code == 202
    body = response.json()
    assert (body["started"], body["already_running"], body["failed"]) == (2, 0, 0)
    assert [r["slot"] for r in body["runs"]] == [1, 2]
    [sent] = workflow.starts
    assert (sent.mce, sent.infra_env, sent.count, sent.namespace) == (SITE1_A, R650, 2, None)


async def test_a_named_start_sends_server_scans_spelling(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeAddServerWorkflow
) -> None:
    response = await fleet.post(
        f"{POOL}/add-servers", json={"server_names": [FREE.lower()]}, headers=auth(support.ALICE)
    )
    assert response.status_code == 202
    assert workflow.starts[0].server_names == (FREE,)


async def test_a_locked_server_is_refused_for_a_named_install_and_nothing_starts(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeAddServerWorkflow
) -> None:
    response = await fleet.post(
        f"{POOL}/add-servers",
        json={"server_names": [FREE, LOCKED]},
        headers=auth(support.ALICE),
    )
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert response.json()["details"]["problems"] == [
        f"{LOCKED}: locked by add-server-to-mce until 2026-11-13T18:00:00+00:00"
    ]
    assert workflow.starts == []


@pytest.mark.parametrize(
    "body",
    [{}, {"count": 1, "server_names": [FREE]}, {"count": 0}, {"count": 21}, {"server_names": []}],
)
async def test_a_body_with_neither_or_both_or_out_of_range_is_422(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, body: dict[str, object]
) -> None:
    response = await fleet.post(f"{POOL}/add-servers", json=body, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (AddServerAlreadyRunningError("every slot busy"), 409, "ADD_SERVER_ALREADY_RUNNING"),
        (AddServerRefusedError("refused", ["count: too many"]), 422, "VALIDATION_ERROR"),
        (WorkflowsUnavailableError("nothing was started"), 502, "DEPENDENCY_UNAVAILABLE"),
        (AmbiguousStartError("no answer: look at the runs"), 504, "AMBIGUOUS_WRITE"),
    ],
)
async def test_the_orchestrators_answers_become_problems(
    fleet: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    workflow: FakeAddServerWorkflow,
    error: Exception,
    status: int,
    code: str,
) -> None:
    workflow.fail_start = error  # ty: ignore[invalid-assignment]
    response = await fleet.post(
        f"{POOL}/add-servers", json={"count": 1}, headers=auth(support.ALICE)
    )
    assert (response.status_code, response.json()["code"]) == (status, code)
    assert len(workflow.starts) == 1, "never retried"


# ── Who, and when it is off ──────────────────────────────────────────────────


async def test_everyone_signed_in_reads_and_only_admins_add(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeAddServerWorkflow
) -> None:
    viewer = auth(support.VIEWER)
    for path in ("/api/day1/inventory", "/api/day1/inventory/runs", f"{POOL}/candidates"):
        response = await fleet.get(path, headers=viewer)
        assert response.status_code == 200, path
        assert (await fleet.get(path)).status_code == 401, f"{path} needs a session"
    response = await fleet.post(f"{POOL}/add-servers", json={"count": 1}, headers=viewer)
    assert (response.status_code, response.json()["code"]) == (403, "FORBIDDEN")
    assert workflow.starts == []


async def test_without_server_scan_the_page_is_not_available(
    support: Any, gitlab: InMemoryGitLab, clock: Any, mce: FakeHubApi, auth: Auth
) -> None:
    app = app_of(support, gitlab, clock, hub=mce, inventory=None, workflow=None)
    async for client in serve(app):
        response = await client.get("/api/day1/inventory", headers=auth(support.ALICE))
        assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
        assert "SERVER_SCAN_URL" in response.json()["detail"]


async def test_adding_off_says_why_and_answers_501_and_runs_need_the_orchestrator(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    mce: FakeHubApi,
    inventory: FakeServerInventory,
    workflow: FakeAddServerWorkflow,
    auth: Auth,
) -> None:
    admin = auth(support.ALICE)
    app = app_of(support, gitlab, clock, hub=mce, inventory=inventory, workflow=workflow)
    async for client in serve(app):
        body = (await client.get("/api/day1/inventory", headers=admin)).json()
        assert body["add_servers"]["available"] is False
        assert "DAY1_ADD_SERVERS" in body["add_servers"]["detail"]
        response = await client.post(f"{POOL}/add-servers", json={"count": 1}, headers=admin)
        assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
    app = app_of(support, gitlab, clock, hub=mce, inventory=inventory, workflow=None)
    async for client in serve(app):
        body = (await client.get("/api/day1/inventory", headers=admin)).json()
        assert body["runs"]["available"] is False
        response = await client.get("/api/day1/inventory/runs", headers=admin)
        assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
    assert workflow.starts == []


async def test_without_live_status_the_pools_are_unknown_and_adding_is_not_offered(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    inventory: FakeServerInventory,
    workflow: FakeAddServerWorkflow,
    auth: Auth,
) -> None:
    admin = auth(support.ALICE)
    app = app_of(
        support, gitlab, clock, hub=None, inventory=inventory, workflow=workflow,
        DAY1_ADD_SERVERS=True,
    )  # fmt: skip
    async for client in serve(app):
        body = (await client.get("/api/day1/inventory", headers=admin)).json()
        site1_a = next(m for m in body["mces"] if m["mce"] == SITE1_A)
        assert [p["infra_env"] for p in site1_a["pools"]] == [None]
        assert "CLUSTER_STATUS_ENABLED" in site1_a["infra_envs_error"]
        assert body["add_servers"]["available"] is False
        response = await client.post(f"{POOL}/add-servers", json={"count": 1}, headers=admin)
        assert response.status_code == 501
    assert workflow.starts == []


async def test_server_scan_down_is_502(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, inventory: FakeServerInventory
) -> None:
    inventory.unavailable = True
    response = await fleet.get("/api/day1/inventory", headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")


class MovingClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


async def test_a_reused_slot_shows_its_read_on_the_newest_run_only(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    mce: FakeHubApi,
    inventory: FakeServerInventory,
    auth: Auth,
) -> None:
    moving = MovingClock()
    workflow = FakeAddServerWorkflow(inventory, clock=moving, phase_seconds=1)
    app = app_of(
        support, gitlab, clock, hub=mce, inventory=inventory, workflow=workflow,
        DAY1_ADD_SERVERS=True,
    )  # fmt: skip
    admin = auth(support.ALICE)
    pool = f"/api/day1/inventory/mces/{SITE1_A}/infra-envs/dell-r760-site1-64c-512gb-20tb"
    async for client in serve(app):
        await client.post(f"{pool}/add-servers", json={"count": 1}, headers=admin)
        moving.now += timedelta(minutes=5)
        await client.get("/api/day1/inventory", headers=admin)  # the first run completes
        await client.post(f"{pool}/add-servers", json={"count": 1}, headers=admin)
        moving.now += timedelta(seconds=1.5)
        newer, older = (await client.get("/api/day1/inventory/runs", headers=admin)).json()["runs"]
    assert newer["workflow_id"] == older["workflow_id"], "the pool's first slot, twice"
    assert (newer["status"], newer["phase"]) == ("running", "acquiring-server")
    assert newer["server_name"] == "ocp-dell-r760-site1-64c-512gb-20tb-DLFAKE0802"
    assert (older["status"], older["phase"], older["server_name"]) == ("completed", None, None)
