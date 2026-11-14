"""The Jobs page: server-scan's CronJobs, their runs and logs (ADR-0048's 3.32.0 amendment).

server-scan's ``GET /api/v1/jobs`` and a pod's log (its ``JobsOverview``,
``CronJobOut``, ``JobOut``, ``PodOut`` and ``PodLogs`` in
``backend/app/api/v1/job_schemas.py``, team-redbull/server-scan at 92146d3,
its ADR-0055): the CronJobs it may start (labelled
``server-scan.io/triggerable``), each with its recent Jobs, newest first, and
their pods. ``POST /api/v1/jobs/{cronjob}/run`` answers the new Job in the
same shape. server-scan serves all of it to its admin role only, so day1
reads it with server-scan's admin token (``jobs_detail``). Typed in its
shape, with its port's defaults, so the web's port of server-scan's
TypeScript reads day1's answer as it is. Read strictly (``SHAPE``): a value
of the wrong type fails the read, never becomes a blank. server-scan's words
(a state, a phase, a backend) and Kubernetes' timestamps stay strings, so a
word it adds later still reaches the page.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel

from wingman_day1.domain.server_scan_hardware import SHAPE
from wingman_day1.domain.server_scan_servers import ADMIN_SETTING
from wingman_day1.domain.server_scan_tokens import token_detail

JOBS_OFF: Final = (
    "Jobs needs server-scan's admin token: add the key admin-token to the server-scan Secret "
    f"and restart day1 ({ADMIN_SETTING})."
)
K8S_NAME: Final = r"^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$"
"""A Kubernetes object's name (a DNS-1123 subdomain): a CronJob's, a Job's, a pod's."""
K8S_NAME_MAX: Final = 253
LOG_TAIL: Final = 500
"""The lines server-scan's page asks for, and day1's default."""
LOG_TAIL_MAX: Final = 100_000
"""server-scan's own bound on ``tail``; it caps it lower (``INVENTORY_JOBS_LOG_TAIL_MAX``)."""


class JobPod(BaseModel):
    """One pod of a Job."""

    model_config = SHAPE

    name: str
    phase: str
    """Kubernetes' pod phase: ``Pending``, ``Running``, ``Succeeded``, ``Failed``, ``Unknown``."""
    started_at: str | None = None


class JobRun(BaseModel):
    """One Job of a CronJob, scheduled or started by hand."""

    model_config = SHAPE

    name: str
    created_at: str | None
    started_at: str | None
    finished_at: str | None
    active: int
    succeeded: int
    failed: int
    state: str
    """``active``, ``succeeded``, ``failed`` or ``pending`` (unfinished, no pod running)."""
    manual: bool
    triggered_by: str | None
    """The actor server-scan wrote on a Job started by hand: Wingman's token, never the person."""
    pods: tuple[JobPod, ...] = ()
    """Oldest first."""


class CronJob(BaseModel):
    """One CronJob server-scan may start, and its recent Jobs."""

    model_config = SHAPE

    name: str
    schedule: str
    suspend: bool
    last_schedule_time: str | None
    last_successful_time: str | None
    warning: str | None
    """What running it can do (its annotation ``server-scan.io/trigger-warning``)."""
    active: bool
    """It has an unfinished Job, so server-scan refuses another start (its 409)."""
    jobs: tuple[JobRun, ...] = ()
    """Newest first."""
    enabled: bool = True
    """Its ``enabled`` flag in the deployment's values.yaml; one the catalog does not know is on."""
    deployed: bool = True
    """Whether the CronJob exists (one switched off in values.yaml does not)."""


class JobsOverview(BaseModel):
    """``GET /api/v1/jobs``: whether the deployment lets its UI start Jobs, and the CronJobs."""

    model_config = SHAPE

    enabled: bool
    """``False`` (with ``backend`` ``off``, no CronJob) when server-scan has the feature off."""
    backend: str
    """``kubernetes``, ``fake`` (server-scan's simulated jobs) or ``off``."""
    namespace: str | None
    cronjobs: tuple[CronJob, ...] = ()
    """By name."""


class PodLogs(BaseModel):
    """The last lines of one pod's log."""

    model_config = SHAPE

    pod: str
    tail: int
    """The lines asked for; server-scan caps what it sends."""
    text: str


def jobs_detail(*, viewer_token: bool, admin_token: bool) -> str | None:
    """Why the Jobs page does not work in this deployment; ``None`` when it does.

    The rule of every token server-scan keeps for a role (``token_detail``),
    as maintenance's: server-scan keeps Jobs for its admins, reads included.
    """
    return token_detail(JOBS_OFF, viewer_token=viewer_token, token=admin_token)
