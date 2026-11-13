"""A flavor's new version reaches each cluster through its own MR (ADR-0044).

When a new version of a flavor lands on the specs repo's main, every cluster
that follows the flavor and is on an older version gets one day1 MR: the
sync to the new version (``SyncService.plan``: its locked values, its
machine configs and the header's ``specVersion``). Each customer merges
theirs when ready; nothing changes on a cluster until its MR merges, so a
change everyone needs never rolls a whole fleet at once, and one customer
can take it today.

**GitLab is the only state.** A run reads the clusters' headers and the
open and closed MRs, and opens what is missing. Each MR's branch names its
flavor, version and cluster (``mr_conventions.rollout_branch``), so a second
run, a restarted replica or a second one finds the branch or its MR instead
of opening another. A write GitLab did not confirm (ADR-0006) is never sent
again blindly: the next run checks the branch first, and opens only the MR
when the commit landed.

Per cluster, against the flavor's newest version:

- ``on_version``: its header is on it; nothing to do.
- ``merge_request_open``: an open MR syncs it there (a rollout's or a
  person's); nothing to do.
- ``declined``: its rollout MR for that version was closed unmerged; no new
  one opens (a person can still sync it by hand).
- ``needs_decision``: the sync cannot change it without a person (a
  nodepool's hardware, a position the file lacks, a file Wingman cannot
  edit); no MR, the reasons are listed.
- ``pending``: an MR will open. ``failed``: this replica's last attempt
  failed; the next run tries again (a read-triggered one after
  ``RETRY_AFTER``).

A run opens the pending MRs a few at a time (``MAX_ROLLOUT_CONCURRENCY``),
and once GitLab stops answering it starts no more. An open sync MR of the
cluster to an older version is closed, with a comment pointing to the new
one. Add-ons the new version needs and the cluster lacks are asked of day2
first (one MR per team), and the day1 MR links them.

Runs start right after Wingman merges a flavor's MR, from the specs
project's webhook, from an admin's Reconcile, and when the status is read
with work pending. They run in the background of the replica that was
asked; one per flavor at a time, again at once if asked while running.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from wingman_core.domain.errors import (
    AlreadyExistsError,
    AmbiguousWriteError,
    GitError,
    GitUnavailableError,
)
from wingman_core.domain.merge_request import MergeRequest, MRState
from wingman_core.domain.mr_conventions import ROLLOUT_LABEL, WINGMAN_LABEL, rollout_branch
from wingman_core.domain.users import Role, User
from wingman_core.ports.clock import Clock
from wingman_day1.application.clusters import ClusterFile, ClusterService
from wingman_day1.application.drift import DriftService
from wingman_day1.application.machine_configs import MachineConfigService
from wingman_day1.application.open_syncs import OpenSyncs, open_syncs, supersede
from wingman_day1.application.specs import SpecCatalog
from wingman_day1.application.sync import Rebooting, Removal, SyncPlan, SyncService, sync_summary
from wingman_day1.domain.addons import Day2InstallRequest, RequestedAddon
from wingman_day1.domain.changes import ClusterAction, ClusterChange
from wingman_day1.domain.errors import (
    Day2UnavailableError,
    InvalidInputError,
    InvalidSpecError,
    ResourceNotFoundError,
    UneditableFileError,
)
from wingman_day1.domain.machine_configs import MachineConfigCatalog
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.rollout import RolloutOutcome, RolloutTrigger
from wingman_day1.domain.specs import ClusterSpec, parse_spec
from wingman_day1.ports import Day2Installs, RepoReads, RolloutEvents, RolloutMergeRequests

logger = logging.getLogger(__name__)

ROLLOUT_USER: Final = User(
    username="system:wingman-rollout", role=Role.ADMIN, full_name="Wingman rollout"
)
"""Who opens a rollout's MRs: the footer's author, so any person may approve them."""
MAX_ROLLOUT_CONCURRENCY: Final = 4
"""MRs a run opens at once, as an import does (ADR-0044)."""
CLOSED_ROLLOUTS_LIMIT: Final = 2000
"""Closed rollout MRs read, newest first, to find the declined ones of the newest version."""
RETRY_AFTER: Final = timedelta(minutes=5)
"""How long a failed cluster waits before a read-triggered run tries it again."""
_PLAN_CACHE: Final = 10_000


class RolloutState(StrEnum):
    """Where one cluster is in its flavor's rollout of the newest version."""

    ON_VERSION = "on_version"
    MERGE_REQUEST_OPEN = "merge_request_open"
    PENDING = "pending"
    NEEDS_DECISION = "needs_decision"
    DECLINED = "declined"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ClusterRollout:
    """One cluster that follows the flavor, and where its update stands."""

    cluster: ClusterFile
    state: RolloutState
    merge_request: MergeRequest | None = None
    """The open MR (``merge_request_open``) or the closed one (``declined``)."""
    reasons: tuple[str, ...] = ()
    plan: SyncPlan | None = None
    """What its MR changes (pending and failed clusters)."""


@dataclass(frozen=True, slots=True)
class RolloutRun:
    """One run on this replica: what started it, when, and what it did."""

    trigger: RolloutTrigger
    version: str | None
    started_at: datetime
    finished_at: datetime | None = None
    opened: int = 0
    failed: int = 0


@dataclass(frozen=True, slots=True)
class RolloutStatus:
    """A flavor's rollout of its newest version, from GitLab's state."""

    spec_name: str
    version: str | None
    """The flavor's newest version; ``None`` when its file cannot be read."""
    clusters: tuple[ClusterRollout, ...]
    running: bool = False
    last_run: RolloutRun | None = None

    def counts(self) -> dict[RolloutState, int]:
        """How many clusters are in each state."""
        return {s: sum(1 for c in self.clusters if c.state is s) for s in RolloutState}


@dataclass(frozen=True, slots=True)
class ClusterRolls:
    """A cluster whose MR rolls nodes: its nodepools and how."""

    ref: ClusterRef
    rebooting: tuple[Rebooting, ...]


@dataclass(frozen=True, slots=True)
class ClusterRemovals:
    """A cluster whose MR removes machine configs."""

    ref: ClusterRef
    removals: tuple[Removal, ...]


@dataclass(frozen=True, slots=True)
class ClusterDecision:
    """A cluster that gets no MR until a person syncs it, and why."""

    ref: ClusterRef
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RolloutPreview:
    """What merging a flavor's MR will open, before it is merged (the approve page)."""

    applies: bool
    reason: str | None
    spec_name: str
    version: str | None
    current_version: str | None
    following: int = 0
    opens: int = 0
    already_on_version: int = 0
    needs_decision: tuple[ClusterDecision, ...] = ()
    rolls_nodes: tuple[ClusterRolls, ...] = ()
    removes_configs: tuple[ClusterRemovals, ...] = ()
    adds_addons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Failure:
    reason: str
    at: datetime


@dataclass(frozen=True, slots=True)
class _Snapshot:
    spec: ClusterSpec
    catalog: MachineConfigCatalog
    syncs: OpenSyncs
    clusters: tuple[ClusterRollout, ...]


class RolloutService:
    """Open, per cluster, the MR that takes it to its flavor's newest version."""

    def __init__(
        self,
        clusters: ClusterService,
        specs: SpecCatalog,
        sync: SyncService,
        drift: DriftService,
        machine_configs: MachineConfigService,
        day1: RepoReads,
        writer: RolloutMergeRequests,
        *,
        day2: Day2Installs | None,
        events: RolloutEvents,
        clock: Clock,
        concurrency: int = MAX_ROLLOUT_CONCURRENCY,
    ) -> None:
        """Read clusters and flavors, plan with ``sync``, open MRs through ``writer``.

        ``day2`` opens the add-on MRs a new version needs (``None``: they are
        listed in the day1 MR for a person to install); ``events`` counts runs
        and MRs.
        """
        self._clusters = clusters
        self._specs = specs
        self._sync = sync
        self._drift = drift
        self._machine_configs = machine_configs
        self._day1 = day1
        self._writer = writer
        self._day2 = day2
        self._events = events
        self._clock = clock
        self._concurrency = concurrency
        self._jobs: dict[str, asyncio.Task[None]] = {}
        self._again: dict[str, tuple[RolloutTrigger, bool]] = {}
        self._runs: dict[str, RolloutRun] = {}
        self._failures: dict[tuple[str, str, ClusterRef], _Failure] = {}
        self._plans: dict[tuple[ClusterRef, int, str, str], SyncPlan] = {}
        self._scans: set[asyncio.Task[None]] = set()

    # ── Status ──────────────────────────────────────────────────────────────

    async def status(self, flavor: str) -> RolloutStatus:
        """The rollout of ``flavor``'s newest version; ``ResourceNotFoundError`` if no flavor."""
        snapshot = await self._snapshot(flavor)
        version = snapshot.spec.metadata.version if snapshot else None
        return RolloutStatus(
            flavor,
            version,
            snapshot.clusters if snapshot else (),
            running=flavor in self._jobs,
            last_run=self._runs.get(flavor),
        )

    async def read(self, flavor: str) -> RolloutStatus:
        """The status, and a run started when work is pending (the fallback trigger)."""
        status = await self.status(flavor)
        if not status.running and self._has_work(status):
            self.start(flavor, RolloutTrigger.READ)
            status = replace(status, running=True)
        return status

    async def preview(self, flavor: str, spec: ClusterSpec) -> RolloutPreview:
        """What merging ``spec`` (a new version of ``flavor``) will open, cluster by cluster."""
        current: ClusterSpec | None = None
        with contextlib.suppress(ResourceNotFoundError, InvalidSpecError):
            current = await self._specs.get(flavor)
        version = spec.metadata.version
        following = [c for c in await self._clusters.clusters() if _follows(c, flavor)]
        catalog = await self._machine_configs.catalog()
        on_version = 0
        decisions: list[ClusterDecision] = []
        rolls: list[ClusterRolls] = []
        removes: list[ClusterRemovals] = []
        for cluster in following:
            if cluster.provenance.spec_version == version:
                on_version += 1
                continue
            plan, reasons = await self._try_plan(cluster, spec, catalog)
            if plan is None or plan.problems:
                decisions.append(ClusterDecision(cluster.ref, reasons))
                continue
            if plan.rebooting:
                rolls.append(ClusterRolls(cluster.ref, plan.rebooting))
            if plan.removals:
                removes.append(ClusterRemovals(cluster.ref, plan.removals))
        listed = {str(a.key) for a in current.spec.day2.addons} if current else set()
        return RolloutPreview(
            applies=True,
            reason=None,
            spec_name=flavor,
            version=version,
            current_version=current.metadata.version if current else None,
            following=len(following),
            opens=len(following) - on_version - len(decisions),
            already_on_version=on_version,
            needs_decision=tuple(decisions),
            rolls_nodes=tuple(rolls),
            removes_configs=tuple(removes),
            adds_addons=tuple(
                str(a.key) for a in spec.spec.day2.addons if str(a.key) not in listed
            ),
        )

    # ── Runs ────────────────────────────────────────────────────────────────

    def start(self, flavor: str, trigger: RolloutTrigger, *, force: bool = False) -> bool:
        """Run in the background; ``False`` when one is running (it runs again when done).

        ``force`` retries failed clusters at once (an admin's Reconcile).
        """
        if flavor in self._jobs:
            _, forced = self._again.get(flavor, (trigger, False))
            self._again[flavor] = (trigger, force or forced)
            return False
        self._jobs[flavor] = asyncio.create_task(
            self._job(flavor, trigger, force), name=f"rollout-{flavor}"
        )
        return True

    def start_all(self, trigger: RolloutTrigger) -> None:
        """In the background: a run for each flavor with work pending (the specs project moved)."""
        task = asyncio.create_task(self._start_all(trigger), name="rollout-scan")
        self._scans.add(task)
        task.add_done_callback(self._scans.discard)

    async def wait(self, flavor: str | None = None) -> None:
        """Until no run of ``flavor`` (of any flavor, with ``None``) is going on this replica."""
        while True:
            if flavor is not None:
                pending = [job] if (job := self._jobs.get(flavor)) is not None else []
            else:
                pending = [*self._scans, *self._jobs.values()]
            if not pending:
                return
            await asyncio.gather(*pending, return_exceptions=True)

    async def close(self) -> None:
        """Cancel the runs going on (on shutdown); the next run picks up from GitLab's state."""
        tasks = [*self._scans, *self._jobs.values()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def preview_merge_request(self, flavor: str, *, action: str, sha: str) -> RolloutPreview:
        """What merging a specs MR (``action`` on ``flavor``, its branch at ``sha``) will open."""

        def no(reason: str, version: str | None = None) -> RolloutPreview:
            return RolloutPreview(False, reason, flavor, version, None)

        if action != "update":
            return no(
                "a new flavor has no clusters yet"
                if action == "create"
                else "deleting a flavor opens no merge requests: its clusters keep their files"
            )
        try:
            spec = parse_spec(await self._specs.at(flavor, sha), expected_name=flavor)
        except (ResourceNotFoundError, InvalidSpecError) as exc:
            return no(f"the flavor file on this merge request cannot be read: {exc}")
        current: ClusterSpec | None = None
        with contextlib.suppress(ResourceNotFoundError, InvalidSpecError):
            current = await self._specs.get(flavor)
        if current is not None and current.metadata.version == spec.metadata.version:
            return no(
                f"v{spec.metadata.version} is already the flavor's version on main",
                spec.metadata.version,
            )
        return await self.preview(flavor, spec)

    async def run(self, flavor: str, trigger: RolloutTrigger, *, force: bool = False) -> RolloutRun:
        """One run now: open each pending cluster's MR; ``force`` retries failed ones at once."""
        started = self._clock()
        self._events.run(trigger)
        # GitLab is the state: read the headers and MRs as they are now, not as cached.
        self._day1.forget_files()
        self._day1.forget_merge_requests()
        snapshot = await self._snapshot(flavor)
        if snapshot is None:
            finished = RolloutRun(trigger, None, started, self._clock())
            self._runs[flavor] = finished
            return finished
        version = snapshot.spec.metadata.version
        self._runs[flavor] = RolloutRun(trigger, version, started)
        now = self._clock()
        todo = [
            c
            for c in snapshot.clusters
            if c.state is RolloutState.PENDING
            or (c.state is RolloutState.FAILED and (force or self._cooled(flavor, version, c, now)))
        ]
        outcomes = await self._open_each(flavor, snapshot, todo)
        finished = RolloutRun(
            trigger,
            version,
            started,
            self._clock(),
            opened=sum(
                1 for o in outcomes if o in (RolloutOutcome.OPENED, RolloutOutcome.RECOVERED)
            ),
            failed=sum(
                1
                for o in outcomes
                if o in (RolloutOutcome.FAILED, RolloutOutcome.UNCONFIRMED, RolloutOutcome.NOT_SENT)
            ),
        )
        self._runs[flavor] = finished
        logger.info(
            "rollout of %s v%s (%s): %d opened, %d failed",
            flavor,
            version,
            trigger,
            finished.opened,
            finished.failed,
            extra={"event": "rollout_run", "flavor": flavor, "trigger": str(trigger)},
        )
        return finished

    # ── Internals ───────────────────────────────────────────────────────────

    async def _start_all(self, trigger: RolloutTrigger) -> None:
        try:
            for entry in await self._specs.entries():
                if entry.spec is None or entry.name in self._jobs:
                    continue
                if self._has_work(await self.status(entry.name)):
                    self.start(entry.name, trigger)
        except Exception:  # a background scan reports; the next trigger scans again
            logger.exception("rollout scan stopped", extra={"event": "rollout_scan_failed"})

    async def _job(self, flavor: str, trigger: RolloutTrigger, force: bool) -> None:
        try:
            while True:
                try:
                    await self.run(flavor, trigger, force=force)
                except asyncio.CancelledError:
                    raise
                except Exception:  # a background run reports, the next run starts afresh
                    logger.exception(
                        "rollout of %s stopped", flavor, extra={"event": "rollout_run_failed"}
                    )
                again = self._again.pop(flavor, None)
                if again is None:
                    return
                trigger, force = again
        finally:
            self._jobs.pop(flavor, None)

    def _has_work(self, status: RolloutStatus) -> bool:
        now = self._clock()
        return status.version is not None and any(
            c.state is RolloutState.PENDING
            or (
                c.state is RolloutState.FAILED
                and self._cooled(status.spec_name, status.version, c, now)
            )
            for c in status.clusters
        )

    def _cooled(self, flavor: str, version: str, item: ClusterRollout, now: datetime) -> bool:
        failure = self._failures.get((flavor, version, item.cluster.ref))
        return failure is None or now - failure.at >= RETRY_AFTER

    async def _snapshot(self, flavor: str) -> _Snapshot | None:
        """The clusters that follow ``flavor``, against its newest version; ``None``: no file."""
        try:
            spec = await self._specs.get(flavor)
        except InvalidSpecError:
            return None
        version = spec.metadata.version
        following = [c for c in await self._clusters.clusters() if _follows(c, flavor)]
        syncs = await open_syncs(self._day1)
        closed = await self._day1.merge_requests(
            state=MRState.CLOSED,
            labels=(WINGMAN_LABEL, ROLLOUT_LABEL),
            limit=CLOSED_ROLLOUTS_LIMIT,
        )
        declined = {mr.source_branch: mr for mr in closed}
        catalog = await self._machine_configs.catalog()
        clusters = [
            await self._state(c, spec, catalog, syncs, declined.get(_branch(flavor, version, c)))
            for c in following
        ]
        return _Snapshot(spec, catalog, syncs, tuple(clusters))

    async def _state(
        self,
        cluster: ClusterFile,
        spec: ClusterSpec,
        catalog: MachineConfigCatalog,
        syncs: OpenSyncs,
        closed: MergeRequest | None,
    ) -> ClusterRollout:
        flavor, version = spec.metadata.name, spec.metadata.version
        if cluster.provenance.spec_version == version:
            return ClusterRollout(cluster, RolloutState.ON_VERSION)
        open_mr = syncs.to(cluster.ref.name, flavor, version)
        if open_mr is not None:
            return ClusterRollout(cluster, RolloutState.MERGE_REQUEST_OPEN, open_mr)
        if closed is not None:
            return ClusterRollout(cluster, RolloutState.DECLINED, closed)
        plan, reasons = await self._try_plan(cluster, spec, catalog)
        if plan is None:
            return ClusterRollout(cluster, RolloutState.NEEDS_DECISION, reasons=reasons)
        if plan.problems:
            return ClusterRollout(cluster, RolloutState.NEEDS_DECISION, reasons=plan.problems)
        failure = self._failures.get((flavor, version, cluster.ref))
        if failure is not None:
            return ClusterRollout(
                cluster, RolloutState.FAILED, reasons=(failure.reason,), plan=plan
            )
        return ClusterRollout(cluster, RolloutState.PENDING, plan=plan)

    async def _try_plan(
        self, cluster: ClusterFile, spec: ClusterSpec, catalog: MachineConfigCatalog
    ) -> tuple[SyncPlan | None, tuple[str, ...]]:
        """The sync plan (cached per file content and version), or why there is none."""
        key = (cluster.ref, hash(cluster.content), spec.metadata.name, spec.metadata.version)
        if key in self._plans:
            plan = self._plans[key]
            return plan, plan.problems
        try:
            plan = await self._sync.plan(cluster, spec, catalog, addons=False)
        except UneditableFileError as exc:
            return None, tuple(f"{exc}: {p}" for p in exc.problems) or (str(exc),)
        except InvalidInputError as exc:
            return None, exc.problems or (str(exc),)
        if len(self._plans) >= _PLAN_CACHE:
            self._plans.clear()
        self._plans[key] = plan
        return plan, plan.problems

    async def _open_each(
        self, flavor: str, snapshot: _Snapshot, todo: Sequence[ClusterRollout]
    ) -> list[RolloutOutcome | None]:
        """Each cluster's MR, a few at a time; once GitLab does not answer, no more start."""
        version = snapshot.spec.metadata.version
        limit = asyncio.Semaphore(self._concurrency)
        unanswered: list[str] = []

        async def one(item: ClusterRollout) -> RolloutOutcome | None:
            ref = item.cluster.ref
            key = (flavor, version, ref)
            async with limit:
                if unanswered:
                    reason = (
                        f"not sent: GitLab did not answer for {unanswered[0]}, so this run started "
                        "no more merge requests"
                    )
                    self._failures[key] = _Failure(reason, self._clock())
                    self._events.merge_request(RolloutOutcome.NOT_SENT)
                    return RolloutOutcome.NOT_SENT
                try:
                    merge_request, outcome = await self._open(item, snapshot)
                except AlreadyExistsError:
                    # An MR is open for the branch already: another run or replica opened it.
                    self._failures.pop(key, None)
                    return None
                except GitError as exc:
                    if isinstance(exc, GitUnavailableError | AmbiguousWriteError):
                        unanswered.append(ref.name)
                    unconfirmed = isinstance(exc, AmbiguousWriteError)
                    outcome = RolloutOutcome.UNCONFIRMED if unconfirmed else RolloutOutcome.FAILED
                    reason = (
                        f"GitLab did not confirm the merge request ({exc}); the next run checks "
                        "its branch before sending anything again"
                        if unconfirmed
                        else f"{type(exc).__name__}: {exc}"
                    )
                    self._failures[key] = _Failure(reason, self._clock())
                    self._events.merge_request(outcome)
                    logger.warning(
                        "rollout merge request for %s not opened: %s",
                        ref.name,
                        reason,
                        extra={"event": "rollout_mr_not_opened", "flavor": flavor},
                    )
                    return outcome
            self._failures.pop(key, None)
            self._events.merge_request(outcome)
            done = await supersede(
                self._writer,
                snapshot.syncs.older(ref.name, flavor, version),
                by=merge_request,
                flavor=flavor,
                version=version,
            )
            for _, error in done:
                if error is None:
                    self._events.merge_request(RolloutOutcome.SUPERSEDED)
            return outcome

        return list(await asyncio.gather(*(one(item) for item in todo)))

    async def _open(
        self, item: ClusterRollout, snapshot: _Snapshot
    ) -> tuple[MergeRequest, RolloutOutcome]:
        """The cluster's MR on its branch; only the MR when an earlier run left the commit."""
        cluster, spec = item.cluster, snapshot.spec
        plan = item.plan
        if plan is None:  # pending and failed items carry their plan
            raise InvalidInputError(f"{cluster.ref.name} has no sync plan")
        branch = _branch(spec.metadata.name, spec.metadata.version, cluster)
        recovered = await self._writer.branch_exists(branch)
        addon_lines = await self._addons(cluster, spec, snapshot.catalog)
        change = ClusterChange(
            action=ClusterAction.SYNC,
            cluster=cluster.ref,
            requested_by=ROLLOUT_USER,
            summary=sync_summary(plan, preface=_preface(cluster, spec), addon_lines=addon_lines),
            content=plan.content,
            last_commit_id=cluster.last_commit_id,
            spec_name=spec.metadata.name,
            spec_version=spec.metadata.version,
        )
        if recovered:
            merge_request = await self._writer.open_for_branch(change, branch=branch)
            return merge_request, RolloutOutcome.RECOVERED
        return await self._writer.open(change, branch=branch), RolloutOutcome.OPENED

    async def _addons(
        self, cluster: ClusterFile, spec: ClusterSpec, catalog: MachineConfigCatalog
    ) -> list[str]:
        """Ask day2 for the add-ons the version needs and the cluster lacks; lines for the MR."""
        if not spec.spec.day2.addons:
            return []
        found = await self._drift.against(cluster, spec, catalog)
        flavor = f"`{spec.metadata.name}` v{spec.metadata.version}"
        if found.error is not None:
            return [
                f"Whether the add-ons flavor {flavor} lists are installed is unknown "
                f"({found.error}); once this merges, the cluster's Add-ons tab installs any "
                "that are missing."
            ]
        missing = found.addon_drift
        if not missing:
            return []
        names = ", ".join(f"`{a.team}/{a.name}`" for a in missing)
        if self._day2 is None:
            return [
                f"Add-ons flavor {flavor} lists that this cluster lacks: {names}. Install them "
                "through day2 (the cluster's Add-ons tab)."
            ]
        wanted = {(a.team, a.name) for a in missing}
        try:
            pending = await self._day2.open_installs(cluster.ref)
            have = {(r.team, chart) for r in pending for chart in r.charts}
            asked = [
                RequestedAddon(a.team, a.name, a.expected_version, a.override_values)
                for a in missing
                if (a.team, a.name) not in have
            ]
            result = (
                await self._day2.install(
                    cluster.ref,
                    asked,
                    message=f"Flavor {spec.metadata.name} v{spec.metadata.version} lists these "
                    f"add-ons; installed with {cluster.ref.name}'s rollout MR in day1",
                )
                if asked
                else None
            )
        except Day2UnavailableError as exc:
            return [
                f"Add-ons flavor {flavor} lists that this cluster lacks: {names}. Day2 did not "
                f"answer ({exc}), so their install MRs were not opened; install them from the "
                "cluster's Add-ons tab."
            ]
        linked: list[Day2InstallRequest] = [
            r for r in pending if any((r.team, c) in wanted for c in r.charts)
        ]
        if result is not None:
            linked += result.opened
        lines = [
            f"Add-ons flavor {flavor} lists that this cluster lacks: {names}. Day2 installs them "
            "in their own MRs; merge them with this one:",
            *(f"- {r.team} !{r.iid}: {r.title} ({r.web_url})" for r in linked),
        ]
        if result is not None and result.failed:
            lines += [
                "Not opened in day2 (install them from the cluster's Add-ons tab):",
                *(f"- {line}" for line in result.failed),
            ]
        return lines


def _follows(cluster: ClusterFile, flavor: str) -> bool:
    return cluster.provenance.spec_name == flavor


def _branch(flavor: str, version: str, cluster: ClusterFile) -> str:
    return rollout_branch(flavor=flavor, version=version, cluster=cluster.ref.name)


def _preface(cluster: ClusterFile, spec: ClusterSpec) -> list[str]:
    flavor, version = spec.metadata.name, spec.metadata.version
    before = cluster.provenance.spec_version or "?"
    return [
        f"**Rollout of flavor `{flavor}` v{version}** to this cluster, which is on v{before}.",
        "",
        "Wingman opened a merge request like this one for each cluster that follows the flavor "
        "when this version was merged (ADR-0044). Merge it when this cluster is ready: nothing "
        "changes on the cluster until it merges. What it removes and which nodes it rolls were "
        f"shown before v{version} was merged. Closing it unmerged declines v{version} for this "
        "cluster: Wingman does not open it again, and a person can still sync it by hand.",
    ]
