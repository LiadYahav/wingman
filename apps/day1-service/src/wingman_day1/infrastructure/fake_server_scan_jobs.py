"""The fake fleet's Jobs: the Jobs page with ``DAY1_FAKE_FLEET=true`` (ADR-0048's 3.32.0 amendment).

server-scan's own fake runner (team-redbull/server-scan at 92146d3,
``backend/app/infrastructure/jobs/fake.py``, decision 18), ported: CronJobs
with a short history each, every run's state judged on the clock (running
until its time is up, then succeeded or failed), and log lines that grow
while a run goes on. ``demo_jobs`` is the local demo's three CronJobs, as a
deployment of server-scan's charts has them: two collectors (one running
now) and the events prune. Nothing here is real.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from wingman_core.ports.clock import Clock, system_clock
from wingman_day1.domain.errors import ServerScanJobNotFoundError
from wingman_day1.domain.server_scan_jobs import CronJob, JobPod, JobRun, JobsOverview, PodLogs

NAMESPACE: Final = "server-scan"
OPENMANAGE_WARNING: Final = (
    "This run can restart an iDRAC (ADR-0050) when a Dell has every disk or NIC UNKNOWN."
)
PRUNE_WARNING: Final = "This run can permanently delete data (stale servers or audit events)."
FEATURE_OFF: Final = "server-scan: Running jobs from the UI is not enabled on this deployment."
_COLLECTOR_LOG: Final = (
    "INFO collector.start source={cronjob}",
    "INFO collector.login ok",
    "INFO collector.fetch servers=2504",
    "INFO ingest.progress done=1000",
    "INFO ingest.progress done=2000",
    "INFO ingest.progress done=2504",
)
_COLLECTOR_DONE: Final = "INFO collector.done created=0 updated=12 unchanged=2492 errors=0"
_COLLECTOR_FAILED: Final = (
    "ERROR collector.fetch timeout after 240s",
    "ERROR collector.failed exit=1",
)
_PRUNE_LOG: Final = (
    "INFO prune.start target=audit_events older_than_days=90",
    "INFO prune.scan matched=1204",
    "INFO prune.delete deleted=1204",
)
_PRUNE_DONE: Final = "INFO prune.done deleted=1204 kept=48211"


@dataclass(frozen=True, slots=True)
class FakeRun:
    """A seeded run: how long before start-up it began, how long it runs, and how it ends."""

    ago: timedelta
    seconds: float = 240.0
    ok: bool = True


@dataclass(frozen=True, slots=True)
class FakeCronJob:
    """A CronJob the fake server-scan may start, and its seeded runs."""

    name: str
    schedule: str
    warning: str | None = None
    runs: tuple[FakeRun, ...] = ()
    prune: bool = False
    """Its log reads as a prune's, not a collector's."""


@dataclass(frozen=True, slots=True)
class _Job:
    """One fake Job: when it started, for how long, how it ends, and who started it by hand."""

    name: str
    started: datetime
    seconds: float
    ok: bool
    manual: bool = False
    triggered_by: str | None = None

    @property
    def pod(self) -> str:
        return f"{self.name}-x7k2p"


class FakeJobs:
    """server-scan's Jobs in memory; ``enabled=False`` is a server-scan with the feature off."""

    def __init__(
        self,
        cronjobs: Iterable[FakeCronJob] = (),
        *,
        enabled: bool = True,
        clock: Clock = system_clock,
    ) -> None:
        """Seed each CronJob's runs at ``clock()``, as server-scan's fake seeds them at start-up."""
        self._cronjobs = {cronjob.name: cronjob for cronjob in cronjobs}
        self.enabled = enabled
        self._clock = clock
        now = clock()
        self._jobs = {
            cronjob.name: [_scheduled(cronjob.name, now - run.ago, run) for run in cronjob.runs]
            for cronjob in self._cronjobs.values()
        }

    def overview(self) -> JobsOverview:
        """``GET /api/v1/jobs``: the CronJobs by name, each one's Jobs newest first."""
        if not self.enabled:
            return JobsOverview(enabled=False, backend="off", namespace=None)
        cronjobs = tuple(self._cronjob(name) for name in sorted(self._cronjobs))
        return JobsOverview(enabled=True, backend="fake", namespace=NAMESPACE, cronjobs=cronjobs)

    def logs(self, cronjob: str, job: str, pod: str, *, tail: int) -> PodLogs:
        """A pod's last ``tail`` lines, growing while its Job runs; not of that chain: not found."""
        found = next((j for j in self._of(cronjob) if j.name == job and j.pod == pod), None)
        if found is None:
            raise ServerScanJobNotFoundError("server-scan: No such Job or pod for that CronJob.")
        lines = self._log(self._cronjobs[cronjob], found)
        return PodLogs(pod=pod, tail=tail, text="\n".join(lines[-tail:]) + "\n")

    def _of(self, cronjob: str) -> list[_Job]:
        if not self.enabled:
            raise ServerScanJobNotFoundError(FEATURE_OFF)
        return self._jobs.get(cronjob, [])

    def _cronjob(self, name: str) -> CronJob:
        cronjob = self._cronjobs[name]
        jobs = sorted((self._run(job) for job in self._jobs[name]), key=_created, reverse=True)
        scheduled = [job for job in jobs if not job.manual]
        succeeded = [job for job in jobs if job.state == "succeeded"]
        return CronJob(
            name=name,
            schedule=cronjob.schedule,
            suspend=False,
            last_schedule_time=scheduled[0].created_at if scheduled else None,
            last_successful_time=succeeded[0].finished_at if succeeded else None,
            warning=cronjob.warning,
            active=any(job.state == "active" for job in jobs),
            jobs=tuple(jobs),
        )

    def _running(self, job: _Job) -> bool:
        return (self._clock() - job.started).total_seconds() < job.seconds

    def _run(self, job: _Job) -> JobRun:
        """A fake Job in server-scan's shape, by how long it has run."""
        running = self._running(job)
        state = "active" if running else ("succeeded" if job.ok else "failed")
        phase = {"active": "Running", "succeeded": "Succeeded", "failed": "Failed"}[state]
        started = _stamp(job.started)
        return JobRun(
            name=job.name,
            created_at=started,
            started_at=started,
            finished_at=None if running else _stamp(job.started + timedelta(seconds=job.seconds)),
            active=1 if running else 0,
            succeeded=1 if state == "succeeded" else 0,
            failed=1 if state == "failed" else 0,
            state=state,
            manual=job.manual,
            triggered_by=job.triggered_by,
            pods=(JobPod(name=job.pod, phase=phase, started_at=started),),
        )

    def _log(self, cronjob: FakeCronJob, job: _Job) -> list[str]:
        """server-scan's fake lines: a failed run ends in errors, a running one is cut short."""
        steps = [line.format(cronjob=cronjob.name) for line in _steps(cronjob)]
        if self._running(job):
            elapsed = (self._clock() - job.started).total_seconds()
            return steps[: 1 + int(elapsed / job.seconds * (len(steps) - 1))]
        if not job.ok:
            return [*steps[:2], *_COLLECTOR_FAILED]
        return [*steps, _PRUNE_DONE if cronjob.prune else _COLLECTOR_DONE]


def demo_jobs(clock: Clock = system_clock) -> FakeJobs:
    """The local demo's Jobs, seeded at ``clock()``."""
    return FakeJobs(demo_cronjobs(), clock=clock)


def demo_cronjobs() -> list[FakeCronJob]:
    """The demo's CronJobs: a failed run between two good ones, one running now, a prune."""
    hour = timedelta(hours=1)
    return [
        FakeCronJob(
            "server-scan-collectors-collector-openmanage",
            "0 6 * * *",
            OPENMANAGE_WARNING,
            (FakeRun(26 * hour), FakeRun(14 * hour, ok=False), FakeRun(2 * hour)),
        ),
        FakeCronJob(
            "server-scan-collectors-collector-ucs-central",
            "0 5 * * *",
            runs=(FakeRun(25 * hour), FakeRun(timedelta(minutes=4), seconds=15 * 60)),
        ),
        FakeCronJob(
            "server-scan-prune-events",
            "30 3 * * 0",
            PRUNE_WARNING,
            (FakeRun(8 * 24 * hour, seconds=90), FakeRun(24 * hour, seconds=90)),
            prune=True,
        ),
    ]


def _steps(cronjob: FakeCronJob) -> tuple[str, ...]:
    return _PRUNE_LOG if cronjob.prune else _COLLECTOR_LOG


def _scheduled(cronjob: str, started: datetime, run: FakeRun) -> _Job:
    """A scheduled Job, named as Kubernetes names them: the minute it was scheduled for."""
    minute = int(started.timestamp()) // 60
    return _Job(f"{cronjob}-{minute}", started, run.seconds, run.ok)


def _stamp(at: datetime) -> str:
    """An instant as Kubernetes writes one: ``2026-11-14T06:00:00Z``."""
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _created(job: JobRun) -> str:
    return job.created_at or ""
