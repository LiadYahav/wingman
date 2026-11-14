"""The Server Scan area's Jobs page: server-scan's CronJobs, runs and logs (ADR-0048, 3.32.0).

Read through the one ``ServerInventory``, never cached. server-scan keeps
all of it for its admins, reads included, so it works with server-scan's
admin token, or with no token at all (a server-scan with auth off), and is
off with a viewer token alone (``domain.server_scan_jobs.jobs_detail``, the
maintenance toggle's rule): every call then raises
``ServerScanWritesOffError`` with the line naming the key.
"""

from __future__ import annotations

from wingman_day1.domain.errors import ServerScanWritesOffError
from wingman_day1.domain.server_scan_jobs import JobsOverview, PodLogs
from wingman_day1.ports import ServerInventory


class ServerScanJobs:
    """The Jobs page's use cases over server-scan."""

    def __init__(self, inventory: ServerInventory, *, detail: str | None = None) -> None:
        """Read server-scan through ``inventory``; ``detail``: why Jobs is off (``None``: on)."""
        self._inventory = inventory
        self.detail = detail

    async def overview(self) -> JobsOverview:
        """The CronJobs server-scan may start, with their recent runs and pods."""
        self._on()
        return await self._inventory.jobs()

    async def logs(self, cronjob: str, job: str, pod: str, *, tail: int) -> PodLogs:
        """A pod's last ``tail`` lines (server-scan caps them)."""
        self._on()
        return await self._inventory.job_logs(cronjob, job, pod, tail=tail)

    def _on(self) -> None:
        if self.detail is not None:
            raise ServerScanWritesOffError(self.detail)
