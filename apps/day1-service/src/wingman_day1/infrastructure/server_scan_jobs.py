"""server-scan's Jobs for the Jobs page (ADR-0048's 3.32.0 amendment).

``GET /api/v1/jobs`` (the triggerable CronJobs with their recent Jobs and
pods) and ``GET /api/v1/jobs/{cronjob}/runs/{job}/pods/{pod}/logs?tail=``
(one pod's last lines, only along the chain CronJob → its Job → its pod).
server-scan serves its whole ``/api/v1/jobs`` router to its admin role, so
both go with the admin token's header, which the adapter passes (none to a
server-scan with auth off). Read strictly into the domain's models of
server-scan's shapes (``domain/server_scan_jobs.py``): an answer that does
not fit is "unavailable", never a blank. server-scan's 404 (no such CronJob,
Job or pod, or its feature off) is ``ServerScanJobNotFoundError``, in its
own words.

``POST /api/v1/jobs/{cronjob}/run`` (no body) starts a real Job from the
CronJob's template and answers it (``201``); its ``409`` (an unfinished Job)
is ``ServerScanJobRunningError``. Sent once through ``server_scan_writes``
(ADR-0006): unanswered, or accepted in a shape day1 cannot read, it is
``AmbiguousServerScanWriteError``, which says to look at the runs first.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final
from urllib.parse import quote

import httpx

from wingman_day1.domain.errors import ServerScanJobNotFoundError, ServerScanJobRunningError
from wingman_day1.domain.server_scan_jobs import JobRun, JobsOverview, PodLogs
from wingman_day1.infrastructure.server_scan_record import check, fetch, parsed, problem_detail
from wingman_day1.infrastructure.server_scan_writes import accepted, refused, send_once

JOBS_PATH: Final = "/api/v1/jobs"
ADMIN: Final = ("admin token", "SERVER_SCAN_ADMIN_TOKEN")
"""The token a refused Jobs call names."""


def job_path(cronjob: str, *rest: str) -> str:
    """``/api/v1/jobs/<cronjob>/<rest…>``, every name quoted."""
    return "/".join([JOBS_PATH, *(quote(part, safe="") for part in (cronjob, *rest))])


async def read_jobs(client: httpx.AsyncClient, *, headers: Mapping[str, str]) -> JobsOverview:
    """The CronJobs server-scan may start, with their runs; ``enabled: false`` when it has none."""
    what = "listing jobs"
    response = await fetch(client, JOBS_PATH, what=what, headers=headers)
    check(response, what=what, token=ADMIN)
    return parsed(JobsOverview, response, "malformed jobs")


async def read_job_logs(
    client: httpx.AsyncClient,
    cronjob: str,
    job: str,
    pod: str,
    *,
    tail: int,
    headers: Mapping[str, str],
) -> PodLogs:
    """A pod's last ``tail`` lines; not a pod of a Job of that CronJob: not found."""
    what = f"reading the log of {pod}"
    path = job_path(cronjob, "runs", job, "pods", pod, "logs")
    response = await fetch(client, path, what=what, headers=headers, params={"tail": tail})
    if response.status_code == 404:
        raise ServerScanJobNotFoundError(
            problem_detail(response) or f"server-scan has no pod {pod!r} of {job!r} of {cronjob!r}"
        )
    check(response, what=what, token=ADMIN)
    return parsed(PodLogs, response, f"a malformed log of {pod}")


async def start_job(
    client: httpx.AsyncClient, cronjob: str, *, headers: Mapping[str, str]
) -> JobRun:
    """Start a Job of ``cronjob`` now and read it; once, whatever happens."""
    what = f"starting a run of {cronjob}"
    check_first = f"Look at the runs of {cronjob} before starting it again."
    path = job_path(cronjob, "run")
    response = await send_once(
        client, "POST", path, what=what, check_first=check_first, headers=headers
    )
    status = response.status_code
    if status in (200, 201):
        return accepted(response, _job_of, what=what, check_first=check_first)
    if status == 404:
        raise ServerScanJobNotFoundError(
            problem_detail(response) or f"server-scan has no triggerable CronJob {cronjob!r}"
        )
    if status == 409:
        raise ServerScanJobRunningError(
            problem_detail(response) or f"server-scan: {cronjob} already has an unfinished Job."
        )
    raise refused(response, what=what, check_first=check_first)


def _job_of(response: httpx.Response) -> JobRun:
    """The new Job; a shape that does not fit raises ValidationError, a ValueError."""
    return JobRun.model_validate_json(response.content)
