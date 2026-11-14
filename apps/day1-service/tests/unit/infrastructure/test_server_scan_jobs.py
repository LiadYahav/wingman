"""server-scan's Jobs through the adapter, the fake's, and the use case (ADR-0048, 3.32.0).

The answers are in server-scan's shapes (``JobsOverview`` and ``PodLogs`` in
``backend/app/api/v1/job_schemas.py`` at 92146d3, its ADR-0055). server-scan
keeps ``/api/v1/jobs`` for its admins, reads included, so every call goes
with the admin token, or with none to a server-scan with auth off.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.application.server_scan_jobs import ServerScanJobs
from wingman_day1.domain.errors import (
    ServerScanDeniedError,
    ServerScanJobNotFoundError,
    ServerScanUnavailableError,
    ServerScanWritesOffError,
)
from wingman_day1.domain.server_scan_jobs import JOBS_OFF, jobs_detail
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.fake_server_scan_jobs import (
    PRUNE_WARNING,
    FakeCronJob,
    FakeJobs,
    FakeRun,
    demo_cronjobs,
    demo_jobs,
)
from wingman_day1.infrastructure.server_scan import HttpServerInventory

VIEWER = "server-scan-viewer-token-never-shown-0005"
ADMIN = "server-scan-admin-token-never-shown-0005"
CRONJOB = "server-scan-collectors-collector-oneview"
JOB = f"{CRONJOB}-29386440"
POD = f"{JOB}-abcde"
LOGS = f"/api/v1/jobs/{CRONJOB}/runs/{JOB}/pods/{POD}/logs"
T0 = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)


def run(**changes: Any) -> dict[str, Any]:
    """A Job as server-scan dumps it: every field."""
    return {
        "name": JOB,
        "created_at": "2026-11-14T06:00:00Z",
        "started_at": "2026-11-14T06:00:01Z",
        "finished_at": "2026-11-14T06:04:10Z",
        "active": 0,
        "succeeded": 1,
        "failed": 0,
        "state": "succeeded",
        "manual": False,
        "triggered_by": None,
        "pods": [{"name": POD, "phase": "Succeeded", "started_at": "2026-11-14T06:00:01Z"}],
    } | changes


def overview(*cronjobs: dict[str, Any]) -> dict[str, Any]:
    return {"enabled": True, "backend": "kubernetes", "namespace": "ns", "cronjobs": list(cronjobs)}


def cronjob(**changes: Any) -> dict[str, Any]:
    return {
        "name": CRONJOB,
        "schedule": "30 6 * * *",
        "suspend": False,
        "last_schedule_time": "2026-11-14T06:00:00Z",
        "last_successful_time": "2026-11-14T06:04:10Z",
        "warning": None,
        "active": False,
        "jobs": [run()],
        "enabled": True,
        "deployed": True,
    } | changes


def make(
    *answers: httpx.Response | Exception,
    token: str = VIEWER,
    admin_token: str = ADMIN,
    metrics: WingmanMetrics | None = None,
) -> tuple[HttpServerInventory, list[httpx.Request]]:
    sent: list[httpx.Request] = []
    queue = list(answers)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    inventory = HttpServerInventory(
        base_url="http://server-scan-api.inventory.svc:8000",
        token=token,
        admin_token=admin_token,
        metrics=metrics,
        transport=httpx.MockTransport(handler),
        timer=iter(range(1000)).__next__,
    )
    return inventory, sent


# ── The reads ──────────────────────────────────────────────────────────────────


async def test_the_jobs_are_read_whole_with_the_admin_token() -> None:
    inventory, sent = make(httpx.Response(200, json=overview(cronjob())))
    answer = await inventory.jobs()
    (request,) = sent
    assert (request.method, request.url.path) == ("GET", "/api/v1/jobs")
    assert request.headers["authorization"] == f"Bearer {ADMIN}"
    assert answer.model_dump(mode="json") == overview(cronjob())


async def test_with_no_token_at_all_the_jobs_are_read_without_one() -> None:
    inventory, sent = make(httpx.Response(200, json=overview()), token="", admin_token="")
    await inventory.jobs()
    assert "authorization" not in sent[0].headers


async def test_the_feature_off_passes_through() -> None:
    off = {"enabled": False, "backend": "off", "namespace": None, "cronjobs": []}
    inventory, _ = make(httpx.Response(200, json=off))
    answer = await inventory.jobs()
    assert (answer.enabled, answer.backend, answer.cronjobs) == (False, "off", ())


async def test_a_cronjob_before_the_catalog_counts_as_enabled_and_deployed() -> None:
    older = cronjob()
    del older["enabled"], older["deployed"], older["jobs"]
    inventory, _ = make(httpx.Response(200, json=overview(older)))
    (read,) = (await inventory.jobs()).cronjobs
    assert (read.enabled, read.deployed, read.jobs) == (True, True, ())


async def test_a_new_word_of_server_scans_reaches_the_page() -> None:
    answer = overview(cronjob(jobs=[run(state="evicted", pods=[])]))
    inventory, _ = make(httpx.Response(200, json=answer))
    (read,) = (await inventory.jobs()).cronjobs
    assert read.jobs[0].state == "evicted"


@pytest.mark.parametrize(
    "broken",
    [
        {"enabled": "yes"},
        {"cronjobs": [cronjob(active="no")]},
        {"cronjobs": [cronjob(jobs=[run(succeeded="1")])]},
        {"cronjobs": [cronjob(jobs=[run(pods=[{"name": POD}])])]},
        {"cronjobs": None},
    ],
)
async def test_a_malformed_answer_is_unavailable_never_a_blank(broken: dict[str, Any]) -> None:
    inventory, _ = make(httpx.Response(200, json=overview() | broken))
    with pytest.raises(ServerScanUnavailableError, match="malformed jobs"):
        await inventory.jobs()


@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_admin_token_is_denied_and_named(status: int) -> None:
    inventory, _ = make(httpx.Response(status, json={}))
    with pytest.raises(ServerScanDeniedError, match=r"admin token.*SERVER_SCAN_ADMIN_TOKEN"):
        await inventory.jobs()


async def test_server_scan_failing_or_unreachable_is_unavailable() -> None:
    inventory, _ = make(httpx.Response(500, json={}), httpx.ConnectError("refused"))
    with pytest.raises(ServerScanUnavailableError, match="answered 500"):
        await inventory.jobs()
    with pytest.raises(ServerScanUnavailableError, match="unreachable"):
        await inventory.jobs()


async def test_a_pods_log_is_read_by_its_chain_with_its_tail() -> None:
    answer = {"pod": POD, "tail": 500, "text": "INFO collector.done\n"}
    inventory, sent = make(httpx.Response(200, json=answer))
    logs = await inventory.job_logs(CRONJOB, JOB, POD, tail=500)
    (request,) = sent
    assert (request.url.path, request.url.params["tail"]) == (LOGS, "500")
    assert request.headers["authorization"] == f"Bearer {ADMIN}"
    assert logs.model_dump() == answer


async def test_the_names_in_a_logs_path_are_quoted() -> None:
    inventory, sent = make(httpx.Response(200, json={"pod": "p", "tail": 1, "text": ""}))
    await inventory.job_logs("a/b", "j", "p", tail=1)
    assert sent[0].url.raw_path.startswith(b"/api/v1/jobs/a%2Fb/runs/j/pods/p/logs")


async def test_a_pod_not_of_that_chain_is_not_found_in_server_scans_words() -> None:
    words = {"detail": f"{POD!r} is not a pod of {JOB!r}."}
    inventory, _ = make(httpx.Response(404, json=words), httpx.Response(404, text="gone"))
    with pytest.raises(ServerScanJobNotFoundError, match=r"server-scan: '.*-abcde' is not a pod"):
        await inventory.job_logs(CRONJOB, JOB, "r-x", tail=5)
    with pytest.raises(ServerScanJobNotFoundError, match="has no pod"):
        await inventory.job_logs(CRONJOB, JOB, POD, tail=5)


async def test_a_malformed_log_is_unavailable() -> None:
    inventory, _ = make(httpx.Response(200, json={"pod": POD, "tail": "500", "text": ""}))
    with pytest.raises(ServerScanUnavailableError, match="malformed log"):
        await inventory.job_logs(CRONJOB, JOB, POD, tail=500)


async def test_the_reads_are_counted() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    inventory, _ = make(
        httpx.Response(200, json=overview()),
        httpx.Response(403, json={}),
        httpx.Response(404, json={}),
        metrics=metrics,
    )
    await inventory.jobs()
    with pytest.raises(ServerScanDeniedError):
        await inventory.jobs()
    with pytest.raises(ServerScanJobNotFoundError):
        await inventory.job_logs(CRONJOB, JOB, POD, tail=1)

    def count(operation: str, outcome: str) -> float | None:
        labels = {"dependency": "server_scan", "operation": operation, "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert count("list_jobs", "ok") == 1
    assert count("list_jobs", "denied") == 1
    assert count("get_job_logs", "not_found") == 1


# ── The use case: the maintenance toggle's rule ───────────────────────────────


@pytest.mark.parametrize(
    ("viewer", "admin", "off"),
    [(False, False, False), (True, True, False), (False, True, False), (True, False, True)],
)
def test_jobs_need_the_admin_token_unless_server_scan_runs_with_auth_off(
    viewer: bool, admin: bool, off: bool
) -> None:
    assert jobs_detail(viewer_token=viewer, admin_token=admin) == (JOBS_OFF if off else None)
    assert "SERVER_SCAN_ADMIN_TOKEN" in JOBS_OFF


async def test_off_nothing_is_read() -> None:
    # A read would fail as unavailable: off answers before reading.
    jobs = ServerScanJobs(FakeServerInventory(unavailable=True), detail=JOBS_OFF)
    with pytest.raises(ServerScanWritesOffError, match="admin-token"):
        await jobs.overview()
    with pytest.raises(ServerScanWritesOffError):
        await jobs.logs(CRONJOB, JOB, POD, tail=1)


# ── The fake: server-scan's fake runner, ported ───────────────────────────────


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def one_cronjob(runs: list[FakeRun], clock: Clock | None = None) -> FakeServerInventory:
    jobs = FakeJobs([FakeCronJob("c", "0 * * * *", runs=tuple(runs))], clock=clock or Clock())
    return FakeServerInventory(jobs=jobs)


async def test_the_demo_has_three_cronjobs_with_succeeded_failed_and_running_runs() -> None:
    fake = FakeServerInventory(jobs=demo_jobs(Clock()))
    answer = await fake.jobs()
    assert (answer.enabled, answer.backend, answer.namespace) == (True, "fake", "server-scan")
    names = [c.name for c in answer.cronjobs]
    assert names == sorted(names)
    assert len(names) == 3
    openmanage, ucs, prune = answer.cronjobs
    assert [j.state for j in openmanage.jobs] == ["succeeded", "failed", "succeeded"]
    assert "iDRAC" in (openmanage.warning or "")
    assert (ucs.active, ucs.jobs[0].state, ucs.jobs[0].pods[0].phase) == (True, "active", "Running")
    assert ucs.jobs[0].finished_at is None
    assert (prune.warning, prune.active) == (PRUNE_WARNING, False)
    assert openmanage.last_successful_time == openmanage.jobs[0].finished_at


async def test_a_runs_times_are_kubernetes_instants_and_newest_first() -> None:
    (cronjob,) = (await one_cronjob([FakeRun(timedelta(hours=1))]).jobs()).cronjobs
    (job,) = cronjob.jobs
    assert job.created_at == "2026-11-14T08:00:00Z"
    assert job.finished_at == "2026-11-14T08:04:00Z"
    assert job.name == f"c-{int((T0 - timedelta(hours=1)).timestamp()) // 60}"


async def test_a_failed_runs_log_ends_in_errors_and_a_good_one_in_done() -> None:
    fake = FakeServerInventory(jobs=demo_jobs(Clock()))
    openmanage = (await fake.jobs()).cronjobs[0]
    good, failed = openmanage.jobs[0], openmanage.jobs[1]
    failed_log = await fake.job_logs(openmanage.name, failed.name, failed.pods[0].name, tail=500)
    assert failed_log.text.splitlines()[-1] == "ERROR collector.failed exit=1"
    good_log = await fake.job_logs(openmanage.name, good.name, good.pods[0].name, tail=500)
    assert good_log.text.splitlines()[-1].startswith("INFO collector.done")
    assert good_log.text.endswith("\n")


async def test_a_running_log_grows_and_its_run_ends_on_the_clock() -> None:
    clock = Clock()
    fake = one_cronjob([FakeRun(timedelta(seconds=0), seconds=100)], clock)
    (job,) = (await fake.jobs()).cronjobs[0].jobs
    pod = job.pods[0].name
    early = (await fake.job_logs("c", job.name, pod, tail=500)).text.splitlines()
    clock.now = T0 + timedelta(seconds=60)
    later = (await fake.job_logs("c", job.name, pod, tail=500)).text.splitlines()
    assert len(early) < len(later)
    clock.now = T0 + timedelta(seconds=100)
    (done,) = (await fake.jobs()).cronjobs[0].jobs
    assert (done.state, done.finished_at) == ("succeeded", "2026-11-14T09:01:40Z")


async def test_a_logs_tail_is_kept() -> None:
    fake = FakeServerInventory(jobs=demo_jobs(Clock()))
    openmanage = (await fake.jobs()).cronjobs[0]
    job = openmanage.jobs[0]
    logs = await fake.job_logs(openmanage.name, job.name, job.pods[0].name, tail=2)
    assert (logs.tail, len(logs.text.splitlines())) == (2, 2)


@pytest.mark.parametrize("which", ["cronjob", "job", "pod"])
async def test_a_name_not_of_the_chain_is_not_found(which: str) -> None:
    fake = FakeServerInventory(jobs=demo_jobs(Clock()))
    openmanage = (await fake.jobs()).cronjobs[0]
    names = {"cronjob": openmanage.name, "job": openmanage.jobs[0].name}
    names["pod"] = openmanage.jobs[0].pods[0].name
    wrong = copy.copy(names) | {which: "nope"}
    with pytest.raises(ServerScanJobNotFoundError):
        await fake.job_logs(wrong["cronjob"], wrong["job"], wrong["pod"], tail=5)


async def test_the_fake_with_the_feature_off_says_so_and_has_no_log() -> None:
    fake = FakeServerInventory(jobs=FakeJobs(demo_cronjobs(), enabled=False, clock=Clock()))
    answer = await fake.jobs()
    assert (answer.enabled, answer.backend, answer.namespace, answer.cronjobs) == (
        False,
        "off",
        None,
        (),
    )
    with pytest.raises(ServerScanJobNotFoundError, match="not enabled on this deployment"):
        await fake.job_logs("server-scan-prune-events", "x", "y", tail=1)


async def test_a_fake_fleet_down_fails_the_jobs_too() -> None:
    fake = FakeServerInventory(jobs=demo_jobs(Clock()), unavailable=True)
    with pytest.raises(ServerScanUnavailableError):
        await fake.jobs()
