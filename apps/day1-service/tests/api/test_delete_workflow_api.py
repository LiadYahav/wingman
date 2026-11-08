"""The delete-cluster workflow routes (ADR-0033): 501 until the workflow exists, ready after."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from wingman_core.domain.users import User
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.workflows import WorkflowRun

Auth = Callable[[User], dict[str, str]]
HERZI = "ocp4-prod-herzi-site1"
PATH = f"/api/day1/clusters/{HERZI}/delete-workflow"


class FakeDeleteWorkflow:
    """What an orchestrator adapter will do: one run per cluster, named by it."""

    def __init__(self) -> None:
        self.runs: dict[str, WorkflowRun] = {}
        self.requested_by: list[str] = []

    async def latest_run(self, ref: ClusterRef) -> WorkflowRun | None:
        return self.runs.get(ref.name)

    async def start(self, ref: ClusterRef, *, requested_by: User) -> WorkflowRun:
        run = WorkflowRun(f"delete-hosted-cluster-{ref.name}", "running", phase="validating")
        self.runs[ref.name] = run
        self.requested_by.append(requested_by.username)
        return run


@pytest.fixture
def workflow(app: FastAPI) -> FakeDeleteWorkflow:
    fake = FakeDeleteWorkflow()
    app.state.day1 = dataclasses.replace(app.state.day1, delete_workflow=fake)
    return fake


@pytest.mark.parametrize(("method", "body"), [("GET", None), ("POST", {"confirm": True})])
async def test_both_routes_say_not_available_yet_until_the_workflow_exists(
    client: httpx.AsyncClient, auth: Auth, support: Any, method: str, body: dict[str, Any] | None
) -> None:
    response = await client.request(method, PATH, json=body, headers=auth(support.ALICE))
    problem = response.json()
    assert (response.status_code, problem["code"]) == (501, "FEATURE_DISABLED")
    assert "not available yet" in problem["detail"]
    assert "segment is not released" in problem["detail"]


async def test_a_cluster_with_no_run_reads_as_none(
    client: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeDeleteWorkflow
) -> None:
    response = await client.get(PATH, headers=auth(support.VIEWER))
    assert (response.status_code, response.json()) == (200, {"run": None})


async def test_an_admin_starts_a_run_and_reads_it_back(
    client: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeDeleteWorkflow
) -> None:
    started = await client.post(PATH, json={"confirm": True}, headers=auth(support.ALICE))
    run = {
        "workflow_id": f"delete-hosted-cluster-{HERZI}",
        "status": "running",
        "phase": "validating",
        "error": None,
    }
    assert (started.status_code, started.json()) == (202, run)
    assert workflow.requested_by == [support.ALICE.username]
    read = await client.get(PATH, headers=auth(support.VIEWER))
    assert read.json() == {"run": run}


@pytest.mark.parametrize("body", [{}, {"confirm": False}, {"confirm": True, "force": True}])
async def test_a_start_must_be_confirmed_and_nothing_else(
    client: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    workflow: FakeDeleteWorkflow,
    body: dict[str, Any],
) -> None:
    response = await client.post(PATH, json=body, headers=auth(support.ALICE))
    assert response.status_code == 422
    assert workflow.runs == {}


async def test_a_viewer_cannot_start_one(
    client: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeDeleteWorkflow
) -> None:
    response = await client.post(PATH, json={"confirm": True}, headers=auth(support.VIEWER))
    assert response.status_code == 403
    assert workflow.runs == {}


async def test_an_unknown_cluster_is_not_found(
    client: httpx.AsyncClient, auth: Auth, support: Any, workflow: FakeDeleteWorkflow
) -> None:
    response = await client.get(
        "/api/day1/clusters/ocp4-prod-nope-site1/delete-workflow", headers=auth(support.VIEWER)
    )
    assert response.status_code == 404
