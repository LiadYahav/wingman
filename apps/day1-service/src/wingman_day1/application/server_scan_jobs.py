"""The Server Scan area's Jobs page: server-scan's CronJobs, runs and logs (ADR-0048, 3.32.0).

Read through the one ``ServerInventory``, never cached. server-scan keeps
all of it for its admins, reads included, so it works with server-scan's
admin token, or with no token at all (a server-scan with auth off), and is
off with a viewer token alone (``domain.server_scan_jobs.jobs_detail``, the
maintenance toggle's rule): every call then raises
``ServerScanWritesOffError`` with the line naming the key.

Run job is the area's second write. server-scan writes Wingman's token on
the Job, never the person, so each start is logged with the person's name
(``server_scan_audit.recorded``), as maintenance is. Never retried
(ADR-0006): server-scan has no idempotency key, and refuses a second start
only while the first is unfinished.
"""

from __future__ import annotations

from wingman_core.domain.users import User
from wingman_day1.application.server_scan_audit import recorded
from wingman_day1.application.server_scan_guards import admin_only
from wingman_day1.domain.server_scan_jobs import JobRun, JobsOverview, PodLogs
from wingman_day1.ports import ServerInventory


class ServerScanJobs:
    """The Jobs page's use cases over server-scan."""

    def __init__(self, inventory: ServerInventory, *, detail: str | None = None) -> None:
        """Read server-scan through ``inventory``; ``detail``: why Jobs is off (``None``: on)."""
        self._inventory = inventory
        self.detail = detail

    async def overview(self) -> JobsOverview:
        """The CronJobs server-scan may start, with their recent runs and pods."""
        admin_only(self.detail)
        return await self._inventory.jobs()

    async def logs(self, cronjob: str, job: str, pod: str, *, tail: int) -> PodLogs:
        """A pod's last ``tail`` lines (server-scan caps them)."""
        admin_only(self.detail)
        return await self._inventory.job_logs(cronjob, job, pod, tail=tail)

    async def run(self, cronjob: str, *, user: User) -> JobRun:
        """Start a Job of ``cronjob`` now, as server-scan's Run job; logged with ``user``."""
        admin_only(self.detail)
        event = {"user": user.username, "cronjob": cronjob}
        start = self._inventory.run_job(cronjob)
        return await recorded(
            start,
            event,
            done="server_scan_job_started",
            unconfirmed="server_scan_job_unconfirmed",
            answered=_named,
        )


def _named(job: JobRun) -> dict[str, str]:
    """What a start's answer adds to its log line: the new Job's name."""
    return {"job": job.name}
