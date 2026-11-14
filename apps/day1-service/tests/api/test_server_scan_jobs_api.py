"""``/api/day1/server-scan/jobs`` (docs/notes/2026-11-13-server-scan-area-api.md §14).

The Server Scan area's Jobs page (ADR-0048's 3.32.0 amendment): server-scan's
CronJobs, their runs and a pod's log, in its shapes. Admins only; with
server-scan's admin token, or none when it runs with auth off, and off (501)
with a viewer token alone; off without server-scan; 502 when it fails or
refuses the token. Built on the fake fleet's demo Jobs.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import AmbiguousServerScanWriteError, ServerScanDeniedError
from wingman_day1.domain.server_scan_jobs import JobRun, JobsOverview
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.fake_server_scan_jobs import demo_jobs
from wingman_day1.ports import ServerInventory

Auth = Callable[[User], dict[str, str]]
JOBS = "/api/day1/server-scan/jobs"
T0 = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
PRUNE = "server-scan-prune-events"
RUNNING = "server-scan-collectors-collector-ucs-central"
CRONJOB_FIELDS = {
    "name",
    "schedule",
    "suspend",
    "last_schedule_time",
    "last_successful_time",
    "warning",
    "active",
    "jobs",
    "enabled",
    "deployed",
}
JOB_FIELDS = {
    "name",
    "created_at",
    "started_at",
    "finished_at",
    "active",
    "succeeded",
    "failed",
    "state",
    "manual",
    "triggered_by",
    "pods",
}


def client(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    inventory: ServerInventory | None,
    **settings: object,
) -> httpx.AsyncClient:
    app = support.build_app(
        gitlab=gitlab,
        hub=None,
        identity=None,
        day2=FakeDay2Addons(),
        clock=clock,
        inventory=inventory,
        **settings,
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://day1.test")


def fleet() -> FakeServerInventory:
    return FakeServerInventory(jobs=demo_jobs(lambda: T0))


def logs_path(cronjob: str, job: str, pod: str) -> str:
    return f"{JOBS}/{cronjob}/runs/{job}/pods/{pod}/logs"


def run_path(cronjob: str) -> str:
    return f"{JOBS}/{cronjob}/run"


class UnansweredFleet(FakeServerInventory):
    """A start sent to server-scan whose answer never came back."""

    async def run_job(self, cronjob: str) -> JobRun:
        self.job_starts.append(cronjob)
        raise AmbiguousServerScanWriteError(
            f"starting a run of {cronjob} was sent to server-scan but no answer came back "
            f"(ReadTimeout): it may have changed. Look at the runs of {cronjob} before starting "
            "it again."
        )


class DeniedFleet(FakeServerInventory):
    async def jobs(self) -> JobsOverview:
        raise ServerScanDeniedError(
            "server-scan refused Wingman's admin token (403) listing jobs: "
            "check SERVER_SCAN_ADMIN_TOKEN"
        )


async def test_only_admins_read_the_jobs(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        anonymous = await http.get(JOBS)
        viewer = await http.get(JOBS, headers=auth(support.VIEWER))
        admin = await http.get(JOBS, headers=auth(support.ALICE))
    assert anonymous.status_code == 401
    assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")
    assert admin.status_code == 200


async def test_the_jobs_come_in_server_scans_shape(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        body = (await http.get(JOBS, headers=auth(support.ALICE))).json()
    assert (body["enabled"], body["backend"], body["namespace"]) == (True, "fake", "server-scan")
    assert len(body["cronjobs"]) == 3
    for cronjob in body["cronjobs"]:
        assert set(cronjob) == CRONJOB_FIELDS
        for job in cronjob["jobs"]:
            assert set(job) == JOB_FIELDS
            assert set(job["pods"][0]) == {"name", "phase", "started_at"}


async def test_a_pods_log_comes_with_its_tail(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    cronjob = (await inventory.jobs()).cronjobs[0]
    job = cronjob.jobs[0]
    path = logs_path(cronjob.name, job.name, job.pods[0].name)
    async with client(support, gitlab, clock, inventory) as http:
        default = await http.get(path, headers=auth(support.ALICE))
        two = await http.get(path, params={"tail": 2}, headers=auth(support.ALICE))
    assert default.status_code == 200
    assert (default.json()["pod"], default.json()["tail"]) == (job.pods[0].name, 500)
    assert "collector.done" in default.json()["text"]
    assert len(two.json()["text"].splitlines()) == 2


async def test_a_pod_server_scan_does_not_have_is_not_found(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        response = await http.get(logs_path("c", "j", "p"), headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
    assert response.json()["detail"].startswith("server-scan:")


@pytest.mark.parametrize(
    "path",
    [
        logs_path("Upper", "j", "p"),
        logs_path("c", "j_x", "p"),
        logs_path("c", "j", "-p"),
        logs_path("c", "j", "a" * 254),
        logs_path("c", "j", "p") + "?tail=0",
        logs_path("c", "j", "p") + "?tail=100001",
    ],
)
async def test_a_name_or_tail_out_of_bounds_is_refused_before_server_scan(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, path: str
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        response = await http.get(path, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    ("tokens", "on"),
    [
        ({}, True),
        ({"server_scan_token": "viewer", "server_scan_admin_token": "admin"}, True),
        ({"server_scan_admin_token": "admin"}, True),
        ({"server_scan_token": "viewer"}, False),
    ],
)
async def test_jobs_need_the_admin_token_unless_server_scan_runs_with_auth_off(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    auth: Auth,
    tokens: dict[str, str],
    on: bool,
) -> None:
    inventory = fleet()
    cronjob = (await inventory.jobs()).cronjobs[0]
    job = cronjob.jobs[0]
    async with client(support, gitlab, clock, inventory, **tokens) as http:
        answers = [
            await http.get(JOBS, headers=auth(support.ALICE)),
            await http.get(
                logs_path(cronjob.name, job.name, job.pods[0].name), headers=auth(support.ALICE)
            ),
        ]
    for answer in answers:
        if on:
            assert answer.status_code == 200
        else:
            assert (answer.status_code, answer.json()["code"]) == (501, "FEATURE_DISABLED")
            assert "admin-token" in answer.json()["detail"]
            assert "SERVER_SCAN_ADMIN_TOKEN" in answer.json()["detail"]
            assert answer.json()["details"]["setting"] == "SERVER_SCAN_ADMIN_TOKEN"


async def test_without_server_scan_the_jobs_are_off(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, None) as http:
        response = await http.get(JOBS, headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
    assert "SERVER_SCAN_URL" in response.json()["detail"]
    assert "setting" not in response.json().get("details", {})


async def test_server_scan_failing_or_refusing_is_502(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, FakeServerInventory(unavailable=True)) as http:
        down = await http.get(JOBS, headers=auth(support.ALICE))
    async with client(support, gitlab, clock, DeniedFleet()) as http:
        denied = await http.get(JOBS, headers=auth(support.ALICE))
    assert (down.status_code, down.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    assert (denied.status_code, denied.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    assert "SERVER_SCAN_ADMIN_TOKEN" in denied.json()["detail"]


async def test_an_admin_starts_a_job_once_and_it_shows_in_the_list(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    async with client(support, gitlab, clock, inventory) as http:
        response = await http.post(run_path(PRUNE), headers=auth(support.ALICE))
        listed = (await http.get(JOBS, headers=auth(support.ALICE))).json()
    assert response.status_code == 201
    job = response.json()
    assert set(job) == JOB_FIELDS
    assert (job["state"], job["manual"], job["triggered_by"]) == ("active", True, "dev")
    prune = next(c for c in listed["cronjobs"] if c["name"] == PRUNE)
    assert (prune["active"], prune["jobs"][0]["name"]) == (True, job["name"])
    assert inventory.job_starts == [PRUNE]


async def test_only_admins_start_a_job(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = fleet()
    async with client(support, gitlab, clock, inventory) as http:
        anonymous = await http.post(run_path(PRUNE))
        viewer = await http.post(run_path(PRUNE), headers=auth(support.VIEWER))
    assert anonymous.status_code == 401
    assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")
    assert inventory.job_starts == []


async def test_a_cronjob_with_an_unfinished_job_is_409_in_server_scans_words(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        response = await http.post(run_path(RUNNING), headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (409, "JOB_ALREADY_RUNNING")
    assert response.json()["detail"].startswith(f"server-scan: {RUNNING} already has an unfinished")


async def test_a_cronjob_server_scan_may_not_start_is_404(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, fleet()) as http:
        response = await http.post(run_path("nope"), headers=auth(support.ALICE))
        bad = await http.post(run_path("Not_A_Name"), headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
    assert "No triggerable CronJob named 'nope'" in response.json()["detail"]
    assert (bad.status_code, bad.json()["code"]) == (422, "VALIDATION_ERROR")


async def test_an_unanswered_start_is_ambiguous_and_never_retried(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    inventory = UnansweredFleet(jobs=demo_jobs(lambda: T0))
    async with client(support, gitlab, clock, inventory) as http:
        response = await http.post(run_path(PRUNE), headers=auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (504, "AMBIGUOUS_WRITE")
    assert "Look at the runs of" in response.json()["detail"]
    assert inventory.job_starts == [PRUNE]


@pytest.mark.parametrize(
    ("tokens", "on"),
    [
        ({}, True),
        ({"server_scan_admin_token": "admin"}, True),
        ({"server_scan_token": "viewer"}, False),
    ],
)
async def test_a_start_needs_the_admin_token_unless_server_scan_runs_with_auth_off(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    auth: Auth,
    tokens: dict[str, str],
    on: bool,
) -> None:
    inventory = fleet()
    async with client(support, gitlab, clock, inventory, **tokens) as http:
        response = await http.post(run_path(PRUNE), headers=auth(support.ALICE))
    if on:
        assert (response.status_code, inventory.job_starts) == (201, [PRUNE])
    else:
        assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
        assert "SERVER_SCAN_ADMIN_TOKEN" in response.json()["detail"]
        assert inventory.job_starts == []
