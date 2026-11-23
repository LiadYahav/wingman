"""Inventory Management's bodies (docs/notes/2026-11-13-inventory-management-api.md, ADR-0057)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wingman_day1.application.inventory import (
    Availability,
    InventoryOverview,
    PoolServers,
    ShownRun,
)
from wingman_day1.domain.add_server import (
    MAX_SERVERS,
    WAIVER_NEEDS_NAMES,
    AddServerRun,
    AddServerStart,
    Origin,
    RunTarget,
    StartedRun,
)
from wingman_day1.domain.herzi_marks import HerziMarks
from wingman_day1.domain.inventory import (
    FROM_DAY1,
    Candidate,
    HardwareCount,
    MceInventory,
    PoolCount,
)
from wingman_day1.domain.servers import ServerRow
from wingman_day1.domain.used_agents import Unguarded


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


class AvailabilityOut(BaseModel):
    """Whether a part of the page works in this deployment, and why not."""

    available: bool
    detail: str | None

    @classmethod
    def of(cls, availability: Availability) -> AvailabilityOut:
        """From the use case."""
        return cls(available=availability.available, detail=availability.detail)


class HardwareOut(BaseModel):
    """Available servers of one vendor and model."""

    vendor: str | None
    model: str | None
    available: int
    usable: int

    @classmethod
    def of(cls, count: HardwareCount) -> HardwareOut:
        """From the domain."""
        return cls(
            vendor=count.vendor, model=count.model, available=count.available, usable=count.usable
        )


class HerziOut(BaseModel):
    """What herzi marked on the pool's InfraEnv (its ``main``): all off when it said nothing."""

    ignored: bool
    """``herzi.redbull.io/ignore``: herzi does not read the pool, and orders nothing."""
    paused: bool
    """``herzi.redbull.io/paused: "true"``: herzi orders nothing (nor removes, by its plan)."""
    blocked_until: str | None
    """``herzi.redbull.io/blocked-until``: an order in flight or unclear, until then."""
    no_hardware_since: str | None
    """Its state's ``capFailAt``, unrecovered: its last order found no hardware."""

    @classmethod
    def of(cls, marks: HerziMarks) -> HerziOut:
        """From the domain."""
        return cls(
            ignored=marks.ignored,
            paused=marks.paused,
            blocked_until=_iso(marks.blocked_until),
            no_hardware_since=_iso(marks.no_hardware_since),
        )


class PoolOut(BaseModel):
    """One InfraEnv pool; ``infra_env`` null: available servers matched to no one InfraEnv."""

    infra_env: str | None
    available: int
    usable: int
    hardware: list[HardwareOut]
    ready: int | None
    """Free servers a pool draw could pick (server-scan's view); null: their names are unknown."""
    needs_fix: int | None
    """Offered free servers a pool draw would not pick: unhealthy or unreachable."""
    total: int
    """``available`` + ``ready`` + ``needs_fix``."""
    server_prefix: str | None
    """``ocp-<flavor>-<size>-<site>-`` from the InfraEnv's agentLabels; null when unknown."""
    label_problems: list[str]
    """Why its agentLabels name no servers: the workflow refuses a pool draw into it."""
    used: list[str]
    """Its used Agents' servers, by name: herzi removes them; never available or in ``total``."""
    herzi: HerziOut

    @classmethod
    def of(cls, pool: PoolCount) -> PoolOut:
        """From the domain."""
        return cls(
            infra_env=pool.infra_env,
            available=pool.available,
            usable=pool.usable,
            hardware=[HardwareOut.of(h) for h in pool.hardware],
            ready=pool.ready,
            needs_fix=pool.needs_fix,
            total=pool.total,
            server_prefix=pool.server_prefix,
            label_problems=list(pool.label_problems),
            used=list(pool.used),
            herzi=HerziOut.of(pool.herzi),
        )


class UnguardedOut(BaseModel):
    """An agent nodepool of the MCE's cluster files that does not exclude every used-Agent key."""

    cluster: str
    nodepool: str
    """Its NodePool's name, as the MCE shows it."""
    infra_envs: list[str]
    missing: list[str]
    """The keys it does not exclude."""
    replace: bool
    """``upgradeType: Replace``: its cluster's merge request leaves it out (ADR-0065)."""

    @classmethod
    def of(cls, pool: Unguarded) -> UnguardedOut:
        """From the domain."""
        return cls(
            cluster=pool.cluster,
            nodepool=pool.nodepool,
            infra_envs=list(pool.infra_envs),
            missing=list(pool.missing),
            replace=pool.replace,
        )


class MceInventoryOut(BaseModel):
    """One MCE: its servers in server-scan and its pools."""

    site: str
    mce: str
    known: bool
    servers: int
    in_clusters: int
    available: int
    usable: int
    pools: list[PoolOut]
    infra_envs: list[str]
    infra_envs_error: str | None
    """Why the MCE's own InfraEnv list is unknown (live status off, the hub unreadable)."""
    infra_envs_from: Literal["mce", "day1"]
    """``mce``: its own list. ``day1``: the InfraEnvs its day1 cluster files name."""
    ready: int
    needs_fix: int
    """The pools' ready and needing a fix, each free server counted once."""
    total: int
    used: int | None
    """Its used Agents, herzi's to remove; null when not read (no live status, ``used_error``)."""
    used_error: str | None
    unguarded: list[UnguardedOut]
    """Its cluster files' agent nodepools that do not exclude every used-Agent key."""

    @classmethod
    def of(cls, mce: MceInventory, unguarded: list[UnguardedOut]) -> MceInventoryOut:
        """From the domain, with its unguarded nodepools."""
        return cls(
            site=mce.site,
            mce=mce.mce,
            known=mce.known,
            servers=mce.servers,
            in_clusters=mce.in_clusters,
            available=mce.available,
            usable=mce.usable,
            pools=[PoolOut.of(pool) for pool in mce.pools],
            infra_envs=list(mce.infra_envs),
            infra_envs_error=mce.infra_envs_error,
            infra_envs_from="day1" if mce.infra_envs_from == FROM_DAY1 else "mce",
            ready=mce.ready,
            needs_fix=mce.needs_fix,
            total=mce.total,
            used=len(mce.used) if mce.used is not None else None,
            used_error=mce.used_error,
            unguarded=unguarded,
        )


class UsedLabelsOut(BaseModel):
    """The Agent label keys that mark a used Agent here, and where they come from."""

    keys: list[str]
    source: Literal["setting", "herzi"]
    """``setting``: ``DAY1_EXCLUDED_AGENT_LABELS``. ``herzi``: herzi's label, the setting empty."""


class InventoryOut(BaseModel):
    """``GET /inventory``: every MCE's pools, and what this deployment offers."""

    mces: list[MceInventoryOut]
    add_servers: AvailabilityOut
    runs: AvailabilityOut
    used_labels: UsedLabelsOut

    @classmethod
    def of(cls, overview: InventoryOverview) -> InventoryOut:
        """From the use case."""
        lacking: dict[str, list[UnguardedOut]] = {}
        for mce, pool in zip(overview.unguarded_mces, overview.unguarded, strict=True):
            lacking.setdefault(mce, []).append(UnguardedOut.of(pool))
        return cls(
            mces=[MceInventoryOut.of(mce, lacking.get(mce.mce, [])) for mce in overview.mces],
            add_servers=AvailabilityOut.of(overview.add_servers),
            runs=AvailabilityOut.of(overview.runs),
            used_labels=UsedLabelsOut(
                keys=list(overview.used_labels),
                source="setting" if overview.excluded else "herzi",
            ),
        )


class LockOut(BaseModel):
    """server-scan's lock (its reservation) while held."""

    holder: str
    mce: str | None
    infra_env: str | None
    expires_at: str | None

    @classmethod
    def of(cls, row: ServerRow) -> LockOut | None:
        """The row's lock, or ``None`` when not held."""
        if row.reserved_by is None:
            return None
        return cls(
            holder=row.reserved_by,
            mce=row.reserved_for_mce,
            infra_env=row.reserved_for_infra_env,
            expires_at=_iso(row.reserved_until),
        )


class CandidateOut(BaseModel):
    """A pool's server, with only what picking it needs."""

    id: str
    name: str
    vendor: str | None
    model: str | None
    health: str
    lock: LockOut | None
    offered: bool
    why_not: str | None
    ready: bool
    """Offered and healthy: a pool draw could pick it. Offered and not ready: it needs a fix."""
    health_problems: list[str]
    """Why a pool draw would not pick it (``health CRITICAL``, ``BMC unreachable``)."""

    @classmethod
    def of(cls, candidate: Candidate) -> CandidateOut:
        """From the domain."""
        row = candidate.row
        return cls(
            id=row.id,
            name=row.name,
            vendor=row.vendor,
            model=row.model,
            health=row.health,
            lock=LockOut.of(row),
            offered=candidate.offered,
            why_not=candidate.why_not,
            ready=candidate.ready,
            health_problems=list(candidate.health_problems),
        )


class CandidatesOut(BaseModel):
    """``GET /inventory/mces/{mce}/infra-envs/{infra_env}/candidates``."""

    mce: str
    infra_env: str
    server_prefix: str | None
    """The name the listed servers start with; null: every free server, not filtered by name."""
    label_problems: list[str]
    """Why the InfraEnv's agentLabels name no servers: the workflow refuses a pool draw into it."""
    candidates: list[CandidateOut]

    @classmethod
    def of(cls, mce: str, found: PoolServers) -> CandidatesOut:
        """From the use case."""
        return cls(
            mce=mce,
            infra_env=found.pool.infra_env,
            server_prefix=found.pool.server_prefix,
            label_problems=list(found.pool.label_problems),
            candidates=[CandidateOut.of(c) for c in found.candidates],
        )


class InventoryRunOut(BaseModel):
    """One add-server run."""

    workflow_id: str
    status: str
    started_at: str | None
    closed_at: str | None
    mce: str | None
    infra_env: str | None
    slot: int | None
    server_name: str | None
    origin: Origin | None
    """``named``: a person. ``pool``: herzi or a person (nothing tells which)."""
    phase: str | None
    error: str | None
    health_checks_waived: list[str]
    """The health checks the run waived (``allow_unhealthy``); empty for every other run."""

    @classmethod
    def of(cls, shown: ShownRun) -> InventoryRunOut:
        """From the use case: the run's own read where made, else the list's entry."""
        listed, target = shown.listed, shown.target
        detail = shown.detail or AddServerRun(listed.workflow_id, listed.status)
        origin = target.origin if target is not None else None
        target = target or RunTarget(mce="", origin=Origin.POOL)
        return cls(
            workflow_id=listed.workflow_id,
            status=detail.status,
            started_at=_iso(listed.started_at),
            closed_at=_iso(listed.closed_at),
            mce=target.mce or None,
            infra_env=target.infra_env,
            slot=target.slot,
            server_name=shown.server_name,
            origin=origin,
            phase=detail.phase,
            error=detail.error,
            health_checks_waived=list(detail.waived),
        )


class InventoryRunsOut(BaseModel):
    """``GET /inventory/runs``: the newest add-server runs."""

    runs: list[InventoryRunOut]


class AddServersIn(BaseModel):
    """``POST .../add-servers``: let the pool pick ``count``, or install these servers."""

    model_config = ConfigDict(extra="forbid")

    count: int | None = Field(default=None, ge=1, le=MAX_SERVERS)
    server_names: list[str] | None = Field(default=None, min_length=1, max_length=MAX_SERVERS)
    allow_unhealthy: bool = False
    """Waive the workflow's health checks for ``server_names``; never on a pool draw."""

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.count is None) == (self.server_names is None):
            raise ValueError("give either count or server_names")
        if self.allow_unhealthy and self.server_names is None:
            raise ValueError(WAIVER_NEEDS_NAMES)
        if self.server_names is not None and not all(
            0 < len(name.strip()) <= 253 for name in self.server_names
        ):
            raise ValueError("a server name is empty or longer than 253 characters")
        return self


class StartedRunOut(BaseModel):
    """The orchestrator's answer for one server."""

    workflow_id: str
    status: str
    server_name: str | None
    slot: int | None
    error: str | None

    @classmethod
    def of(cls, run: StartedRun) -> StartedRunOut:
        """From the domain."""
        return cls(
            workflow_id=run.workflow_id,
            status=run.status,
            server_name=run.server_name,
            slot=run.slot,
            error=run.error,
        )


class AddServersOut(BaseModel):
    """``202``: how many started, were already running or failed, and each run."""

    started: int
    already_running: int
    failed: int
    runs: list[StartedRunOut]

    @classmethod
    def of(cls, result: AddServerStart) -> AddServersOut:
        """From the domain."""
        return cls(
            started=result.started,
            already_running=result.already_running,
            failed=result.failed,
            runs=[StartedRunOut.of(run) for run in result.runs],
        )
