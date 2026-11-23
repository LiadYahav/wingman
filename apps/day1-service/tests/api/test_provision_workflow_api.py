"""Creating through the provision-cluster workflow over HTTP (ADR-0042).

Every create starts the workflow with the rendered file and answers its run
(the merge-request create was removed on 2026-11-23); Wingman shows the run
and keeps no phase list.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import AmbiguousStartError, ProvisionRefusedError
from wingman_day1.infrastructure.fake_provision import FakeProvisionWorkflow

Auth = Callable[[User], dict[str, str]]

NAME = "ocp4-prod-falcon-site1"
CREATE = "/api/day1/clusters"
RUN = f"/api/day1/clusters/{NAME}/provision-run"


class ManualClock:
    """The fake workflow's clock, moved by the test."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, *, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def run_clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def provision(run_clock: ManualClock) -> FakeProvisionWorkflow:
    """The conftest app's provision-cluster, on a clock the test moves."""
    return FakeProvisionWorkflow(clock=run_clock)


async def test_a_create_starts_the_workflow_with_the_rendered_file(
    client: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    provision: FakeProvisionWorkflow,
    gitlab: InMemoryGitLab,
) -> None:
    created = await client.post(CREATE, json=support.create_body(), headers=auth(support.ALICE))
    assert created.status_code == 202, created.text
    body = created.json()
    assert body["workflow_id"] == f"provision-cluster-{NAME}"
    assert body["cluster"] == NAME
    assert body["status"] == "running"
    (started,) = provision.starts
    assert started["cluster"] == "prod-falcon-site1"  # the stem without ocp4-
    assert started["mce"] == "ocp4-prod-mce-site1-a"
    preview = await client.post(
        f"{CREATE}/preview", json=support.create_body(), headers=auth(support.ALICE)
    )
    assert started["content"] == preview.json()["yaml"]  # the file a create would commit
    assert started["content"].startswith("#")  # its provenance header travels as comments
    assert "vlanId" not in started["content"]
    # Wingman opened nothing itself: the workflow opens the merge request
    project = await gitlab.get_project(support.DAY1)
    assert await gitlab.list_merge_requests(project.id, state=None) == []
    assert [b.name for b in await gitlab.list_branches(project.id)] == ["main"]


async def test_the_provisioner_route_is_gone(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    """``GET /clusters/provisioner`` said which way Create went (3.7.0 to 3.55); there is one."""
    gone = await client.get("/api/day1/clusters/provisioner", headers=auth(support.VIEWER))
    assert gone.status_code == 404


async def test_the_run_shows_the_workflows_phase_and_merge_request(
    client: httpx.AsyncClient,
    auth: Auth,
    support: Any,
    run_clock: ManualClock,
) -> None:
    await client.post(CREATE, json=support.create_body(), headers=auth(support.ALICE))
    first = (await client.get(RUN, headers=auth(support.VIEWER))).json()
    assert first["phase"] == "inspecting-target"
    assert first["merge_request_url"] is None
    run_clock.advance(seconds=600)
    later = (await client.get(RUN, headers=auth(support.VIEWER))).json()
    assert (later["status"], later["phase"]) == ("running", "awaiting-merge")
    assert later["merge_request_url"].startswith("https://gitlab.example/")


async def test_a_second_create_while_a_run_goes_is_a_conflict(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    await client.post(CREATE, json=support.create_body(), headers=auth(support.ALICE))
    again = await client.post(CREATE, json=support.create_body(), headers=auth(support.ALICE))
    assert (again.status_code, again.json()["code"]) == (409, "ALREADY_EXISTS")


async def test_the_forms_own_checks_still_run_before_anything_starts(
    client: httpx.AsyncClient, auth: Auth, support: Any, provision: FakeProvisionWorkflow
) -> None:
    bad = support.create_body(name="ocp4-prod-falcon-site1-12")
    refused = await client.post(CREATE, json=bad, headers=auth(support.ALICE))
    assert (refused.status_code, refused.json()["code"]) == (422, "VALIDATION_ERROR")
    assert provision.starts == []


async def test_the_orchestrators_refusal_and_a_lost_answer_reach_the_form(
    client: httpx.AsyncClient, auth: Auth, support: Any, provision: FakeProvisionWorkflow
) -> None:
    provision.fail_start = ProvisionRefusedError(
        "the orchestrator refused to provision prod-falcon-site1",
        ["cluster: at most 24 characters"],
    )
    refused = await client.post(CREATE, json=support.create_body(), headers=auth(support.ALICE))
    problem = refused.json()
    assert (refused.status_code, problem["code"]) == (422, "VALIDATION_ERROR")
    assert problem["details"]["problems"] == ["cluster: at most 24 characters"]
    provision.fail_start = AmbiguousStartError("sent, no answer: it may have started")
    lost = await client.post(CREATE, json=support.create_body(), headers=auth(support.ALICE))
    assert (lost.status_code, lost.json()["code"]) == (504, "AMBIGUOUS_WRITE")


async def test_only_admins_create_and_an_unknown_run_is_not_found(
    client: httpx.AsyncClient, auth: Auth, support: Any
) -> None:
    denied = await client.post(CREATE, json=support.create_body(), headers=auth(support.VIEWER))
    assert denied.status_code == 403
    missing = await client.get(RUN, headers=auth(support.VIEWER))
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")
    bad_name = await client.get(
        "/api/day1/clusters/Not_A_Name/provision-run", headers=auth(support.VIEWER)
    )
    assert bad_name.status_code == 422
