"""Ready and Needs fix, the totals, and installing with health checks waived (ADR-0057, 3.38.0).

A pool's offered free servers are ready (a pool draw could pick them) or
need a fix (unhealthy or unreachable in server-scan). A named install takes
one that needs a fix only with the workflow's ``allow_unhealthy``, which
day1 refuses on a pool draw before anything is sent.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.names import HostedClusterNaming
from wingman_day1.infrastructure.fake_add_server import FakeAddServerWorkflow
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import load_fleet
from wingman_day1.infrastructure.fake_inventory_demo import (
    default_inventory_file,
    load_agent_labels,
    load_inventory_demo,
)
from wingman_day1.infrastructure.fake_mce import default_mce_file, load_fake_mce
from wingman_day1.integrations.server_scan.infrastructure.fakes.inventory import (
    FakeServerInventory,
    default_fleet_file,
)

Auth = Callable[[User], dict[str, str]]
SITE1_A = "ocp4-prod-mce-site1-a"
R650 = "r650-mtl-az1"
POOL = f"/api/day1/inventory/mces/{SITE1_A}/infra-envs/{R650}"
NAMES = "ocp-r650-mtl-site1"
"""What the pool's agentLabels name its servers."""
FREE = f"{NAMES}-dlfake0811"
LOCKED = f"{NAMES}-dlfake0812"
DONOR = f"{NAMES}-dlfake0813"
SICK = f"{NAMES}-dlfake0815"
"""CRITICAL and unreachable in the fixture: it needs a fix."""


class MovingClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def moving() -> MovingClock:
    return MovingClock()


@pytest.fixture
def inventory(moving: MovingClock) -> FakeServerInventory:
    rows = load_fleet(default_fleet_file())[0]
    demo = load_inventory_demo(default_inventory_file(), now=moving())
    return FakeServerInventory([*rows, *demo.rows])


@pytest.fixture
def workflow(inventory: FakeServerInventory, moving: MovingClock) -> FakeAddServerWorkflow:
    labels = load_agent_labels(default_mce_file())
    return FakeAddServerWorkflow(inventory, clock=moving, phase_seconds=1, agent_labels=labels)


@pytest.fixture
async def fleet(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    inventory: FakeServerInventory,
    workflow: FakeAddServerWorkflow,
) -> AsyncIterator[httpx.AsyncClient]:
    rows = load_fleet(default_fleet_file())[0]
    hub = load_fake_mce(default_mce_file(), servers=rows, naming=HostedClusterNaming())
    app: FastAPI = support.build_app(
        gitlab=gitlab, hub=hub, identity=None, day2=FakeDay2Addons(), clock=clock,
        inventory=inventory, add_server=workflow, DAY1_ADD_SERVERS=True,
        SERVER_SCAN_URL="http://server-scan-api.inventory.svc:8000",
        WORKFLOWS_API_URL="http://workflows-orchestrator-api.redbull-workflows.svc:8080",
    )  # fmt: skip
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        yield client


# ── The counts ───────────────────────────────────────────────────────────────


async def test_a_pool_says_what_is_ready_what_needs_a_fix_and_its_total(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    body = (await fleet.get("/api/day1/inventory", headers=auth(support.VIEWER))).json()
    site1_a = next(m for m in body["mces"] if m["mce"] == SITE1_A)
    pools = {p["infra_env"]: p for p in site1_a["pools"]}
    r650 = pools[R650]
    assert (r650["available"], r650["ready"], r650["needs_fix"], r650["total"]) == (0, 1, 1, 2)
    assert "drawable" not in r650
    none = pools[None]
    assert (none["ready"], none["needs_fix"], none["total"]) == (None, None, none["available"])
    named = [
        p for p in site1_a["pools"] if p["ready"] is not None and p["infra_env"] != "r760-mtl-az2"
    ]
    assert site1_a["ready"] == sum(p["ready"] for p in named), "az2 shares az1's servers"
    assert site1_a["needs_fix"] == sum(p["needs_fix"] for p in named)
    assert site1_a["total"] == site1_a["available"] + site1_a["ready"] + site1_a["needs_fix"]


async def test_a_pools_servers_come_ready_first_then_needing_a_fix_with_why_then_the_rest(
    fleet: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    found = (await fleet.get(f"{POOL}/candidates", headers=auth(support.VIEWER))).json()
    listed = [(c["name"], c["ready"], c["offered"]) for c in found["candidates"]]
    assert listed == [
        (FREE, True, True),
        (SICK, False, True),
        (LOCKED, False, False),
        (DONOR, False, False),
    ]
    by_name = {c["name"]: c for c in found["candidates"]}
    assert by_name[SICK]["health_problems"] == ["health CRITICAL", "BMC unreachable"]
    assert (by_name[SICK]["why_not"], by_name[FREE]["health_problems"]) == (None, [])


# ── The waiver ───────────────────────────────────────────────────────────────


async def test_a_pool_draw_with_allow_unhealthy_is_422_and_the_workflow_is_never_called(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeAddServerWorkflow
) -> None:
    response = await fleet.post(
        f"{POOL}/add-servers",
        json={"count": 1, "allow_unhealthy": True},
        headers=auth(support.ALICE),
    )
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert "only for servers named in server_names" in response.text
    assert workflow.starts == []


async def test_a_named_server_that_needs_a_fix_is_installed_with_its_checks_waived_when_asked(
    fleet: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    workflow: FakeAddServerWorkflow,
    moving: MovingClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = auth(support.ALICE)
    with caplog.at_level(logging.INFO, logger="wingman_day1.application.inventory"):
        response = await fleet.post(
            f"{POOL}/add-servers",
            json={"server_names": [SICK], "allow_unhealthy": True},
            headers=admin,
        )
    assert response.status_code == 202
    [sent] = workflow.starts
    assert (sent.server_names, sent.allow_unhealthy, sent.count) == ((SICK,), True, None)
    [started] = [r for r in caplog.records if getattr(r, "event", "") == "servers_add_started"]
    assert started.levelno == logging.WARNING
    assert "with health checks waived" in started.getMessage()
    assert "user=alice" in started.getMessage()
    assert getattr(started, "allow_unhealthy", None) == "true"
    moving.now += timedelta(seconds=1.5)  # past the phase at which the run takes its server
    [run] = (await fleet.get("/api/day1/inventory/runs", headers=admin)).json()["runs"]
    assert (run["status"], run["server_name"]) == ("running", SICK)
    assert run["health_checks_waived"] == [
        "server-scan-health: overall CRITICAL",
        "bmc-reachable: server-scan cannot reach its BMC",
    ]


async def test_without_the_waiver_the_workflow_fails_the_named_run_on_its_health(
    fleet: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    workflow: FakeAddServerWorkflow,
    moving: MovingClock,
) -> None:
    admin = auth(support.ALICE)
    response = await fleet.post(f"{POOL}/add-servers", json={"server_names": [SICK]}, headers=admin)
    assert response.status_code == 202, "day1 starts it: the workflow is the judge"
    assert workflow.starts[0].allow_unhealthy is False
    moving.now += timedelta(seconds=1.5)
    [run] = (await fleet.get("/api/day1/inventory/runs", headers=admin)).json()["runs"]
    assert run["status"] == "failed"
    assert "not healthy: health CRITICAL, BMC unreachable" in run["error"]
    assert run["health_checks_waived"] == []


async def test_a_waiver_never_passes_a_safety_refusal_and_needs_an_admin(
    fleet: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeAddServerWorkflow
) -> None:
    body = {"server_names": [LOCKED], "allow_unhealthy": True}
    response = await fleet.post(f"{POOL}/add-servers", json=body, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")
    assert response.json()["details"]["problems"] == [
        f"{LOCKED}: locked by add-server-to-mce until 2026-11-13T18:00:00+00:00"
    ]
    body = {"server_names": [SICK], "allow_unhealthy": True}
    response = await fleet.post(f"{POOL}/add-servers", json=body, headers=auth(support.VIEWER))
    assert (response.status_code, response.json()["code"]) == (403, "FORBIDDEN")
    assert workflow.starts == []
