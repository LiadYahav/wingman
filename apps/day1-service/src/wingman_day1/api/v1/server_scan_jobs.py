"""The Server Scan area's Jobs page: server-scan's CronJobs, runs and logs (ADR-0048, 3.32.0).

Admins only, as the area (decision 13 of ``docs/ideas/single-pane.md``),
answered in server-scan's own shapes. server-scan keeps its Jobs for its
admins, reads included, so these routes go with its admin token: without it
beside a viewer token they answer 501 naming the key; with no token at all
(server-scan with auth off) they work without one. 501 with
``SERVER_SCAN_URL`` empty, 404 for a CronJob, Job or pod server-scan does not
have (or its feature off), 502 when server-scan fails or refuses the token.
Never cached. Run job is the area's second write, as server-scan's Run job:
never retried, 409 ``JOB_ALREADY_RUNNING`` while the CronJob has an unfinished
Job, 504 ``AMBIGUOUS_WRITE`` when unanswered, logged with the person's name.
The contract: ``docs/notes/2026-11-13-server-scan-area-api.md`` §14.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from wingman_core.web.auth import AdminUser
from wingman_day1.api.deps import ServerScan
from wingman_day1.domain.server_scan_jobs import (
    K8S_NAME,
    K8S_NAME_MAX,
    LOG_TAIL,
    LOG_TAIL_MAX,
    JobRun,
    JobsOverview,
    PodLogs,
)

router = APIRouter(prefix="/api/day1/server-scan/jobs", tags=["server-scan"])
Name = Annotated[str, Path(pattern=K8S_NAME, max_length=K8S_NAME_MAX)]


@router.get("")
async def server_scan_jobs(service: ServerScan, user: AdminUser) -> JobsOverview:
    """The CronJobs server-scan may start, their Jobs and pods; ``enabled: false`` when off."""
    return await service.jobs.overview()


@router.get("/{cronjob}/runs/{job}/pods/{pod}/logs")
async def server_scan_job_logs(
    cronjob: Name,
    job: Name,
    pod: Name,
    service: ServerScan,
    user: AdminUser,
    tail: Annotated[int, Query(ge=1, le=LOG_TAIL_MAX)] = LOG_TAIL,
) -> PodLogs:
    """A pod's last ``tail`` lines, only for a pod of a Job of that CronJob."""
    return await service.jobs.logs(cronjob, job, pod, tail=tail)


@router.post("/{cronjob}/run", status_code=201)
async def run_server_scan_job(cronjob: Name, service: ServerScan, user: AdminUser) -> JobRun:
    """Start a Job of the CronJob now, from its template; logged with the person's name."""
    return await service.jobs.run(cronjob, user=user)
