"""Installing servers without live status (ADR-0057's amendment, 3.19.0).

The orchestrator's own "Install servers" form takes the InfraEnv and the MCE
as typed text; the workflow's first phase (``validating-infraenv``) checks
the InfraEnv is on the MCE. Day1 does the same: the MCE must be a day1 MCE
and the InfraEnv a DNS label, and no MCE read is needed to start a run or to
list a pool's servers. Without the MCE's own InfraEnv list, the pools are the
ones the MCE's day1 cluster files name.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
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

Auth = Callable[[User], dict[str, str]]
SITE1_A = "ocp4-prod-mce-site1-a"
R650 = "dell-r650-site1-96c-768gb"
FREE = "ocp-dell-r650-site1-96c-768gb-DLFAKE0811"
DAY1_POOLS = [
    "dell-r660-site1-128c-1024gb-5tb",
    "dell-r760-site1-64c-512gb-20tb",
    "hp-gen11-site1-64c",
]
"""The InfraEnvs site1-a's cluster files name (lark and heron's ``nodepool[].infraEnvName``)."""
URLS = {
    "SERVER_SCAN_URL": "http://server-scan-api.inventory.svc:8000",
    "WORKFLOWS_API_URL": "http://workflows-orchestrator-api.redbull-workflows.svc:8080",
}


def pool(mce: str, infra_env: str) -> str:
    return f"/api/day1/inventory/mces/{mce}/infra-envs/{infra_env}"


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
    inventory: FakeServerInventory,
    workflow: FakeAddServerWorkflow,
) -> FastAPI:
    return support.build_app(
        gitlab=gitlab,
        hub=hub,
        identity=None,
        day2=FakeDay2Addons(),
        clock=clock,
        inventory=inventory,
        add_server=workflow,
        DAY1_ADD_SERVERS=True,
        **URLS,
    )


@pytest.fixture
async def no_live_status(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    inventory: FakeServerInventory,
    workflow: FakeAddServerWorkflow,
) -> AsyncIterator[httpx.AsyncClient]:
    """The sandbox's shape: server-scan and the orchestrator, no hub (live status off)."""
    app = app_of(support, gitlab, clock, hub=None, inventory=inventory, workflow=workflow)
    async for client in serve(app):
        yield client


# ── The page ─────────────────────────────────────────────────────────────────


async def test_without_live_status_the_pools_are_the_ones_the_day1_files_name(
    no_live_status: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = (await no_live_status.get("/api/day1/inventory", headers=auth(support.ALICE))).json()
    assert body["add_servers"] == {"available": True, "detail": None}, "no live status needed"
    site1_a = next(m for m in body["mces"] if m["mce"] == SITE1_A)
    assert site1_a["infra_envs_from"] == "day1"
    assert "CLUSTER_STATUS_ENABLED" in site1_a["infra_envs_error"]
    assert site1_a["infra_envs"] == DAY1_POOLS
    named = [p["infra_env"] for p in site1_a["pools"] if p["infra_env"] is not None]
    assert named == DAY1_POOLS
    r760 = next(p for p in site1_a["pools"] if p["infra_env"] == DAY1_POOLS[1])
    assert r760["drawable"] == 3, "server-scan's free servers named for the pool"
    assert site1_a["available"] == 6, "the counts stay server-scan's"


async def test_a_hub_that_cannot_be_read_falls_back_to_the_day1_files_and_says_why(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    inventory: FakeServerInventory,
    workflow: FakeAddServerWorkflow,
    auth: Auth,
) -> None:
    hub = FakeHubApi(unavailable=[SITE1_A])
    app = app_of(support, gitlab, clock, hub=hub, inventory=inventory, workflow=workflow)
    async for client in serve(app):
        body = (await client.get("/api/day1/inventory", headers=auth(support.ALICE))).json()
    site1_a = next(m for m in body["mces"] if m["mce"] == SITE1_A)
    assert (site1_a["infra_envs_from"], site1_a["infra_envs"]) == ("day1", DAY1_POOLS)
    assert "unreachable" in site1_a["infra_envs_error"]


async def test_a_pools_servers_are_listed_without_live_status(
    no_live_status: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    response = await no_live_status.get(
        f"{pool(SITE1_A, R650)}/candidates", headers=auth(support.VIEWER)
    )
    assert response.status_code == 200
    found = {c["name"]: c["offered"] for c in response.json()["candidates"]}
    assert found[FREE] is True


# ── Installing ───────────────────────────────────────────────────────────────


async def test_a_pool_draw_starts_without_live_status(
    no_live_status: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeAddServerWorkflow
) -> None:
    response = await no_live_status.post(
        f"{pool(SITE1_A, DAY1_POOLS[1])}/add-servers",
        json={"count": 2},
        headers=auth(support.ALICE),
    )
    assert response.status_code == 202
    assert response.json()["started"] == 2
    [sent] = workflow.starts
    assert (sent.mce, sent.infra_env, sent.count) == (SITE1_A, DAY1_POOLS[1], 2)


async def test_a_named_install_starts_without_live_status(
    no_live_status: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeAddServerWorkflow
) -> None:
    response = await no_live_status.post(
        f"{pool(SITE1_A, R650)}/add-servers",
        json={"server_names": [FREE]},
        headers=auth(support.ALICE),
    )
    assert response.status_code == 202
    assert workflow.starts[0].server_names == (FREE,)


async def test_an_infra_env_no_list_names_is_sent_and_the_workflow_judges_it(
    no_live_status: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeAddServerWorkflow
) -> None:
    typed = "cisco-m6-site1-64c-512gb"
    response = await no_live_status.post(
        f"{pool(SITE1_A, typed)}/add-servers", json={"count": 1}, headers=auth(support.ALICE)
    )
    assert response.status_code == 202
    assert workflow.starts[0].infra_env == typed


@pytest.mark.parametrize("infra_env", ["Dell-R650", "dell_r650", "-dell", "dell-", "a" * 64])
async def test_an_infra_env_that_is_not_a_dns_label_is_422_and_nothing_starts(
    no_live_status: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    workflow: FakeAddServerWorkflow,
    infra_env: str,
) -> None:
    response = await no_live_status.post(
        f"{pool(SITE1_A, infra_env)}/add-servers", json={"count": 1}, headers=auth(support.ALICE)
    )
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert any("InfraEnv" in p for p in response.json()["details"]["problems"])
    assert workflow.starts == []


async def test_an_mce_the_day1_repo_lacks_is_404_and_nothing_starts(
    no_live_status: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeAddServerWorkflow
) -> None:
    response = await no_live_status.post(
        f"{pool('ocp4-prod-mce-nowhere-z', R650)}/add-servers",
        json={"count": 1},
        headers=auth(support.ALICE),
    )
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
    assert workflow.starts == []


async def test_a_viewer_still_cannot_install(
    no_live_status: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeAddServerWorkflow
) -> None:
    response = await no_live_status.post(
        f"{pool(SITE1_A, R650)}/add-servers", json={"count": 1}, headers=auth(support.VIEWER)
    )
    assert (response.status_code, response.json()["code"]) == (403, "FORBIDDEN")
    assert workflow.starts == []
