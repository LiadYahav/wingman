"""Inventory Management: each MCE's servers and pools, as server-scan counts them (ADR-0057).

server-scan's ``openshift_state`` says where a server is: ``AVAILABLE`` (in no
MCE), ``INSTALLED_TO_INVENTORY`` (an Agent in its MCE's inventory, in no
cluster: **available**) or ``INSTALLED`` (in a cluster). An available server
is *usable* by placement's rule (``mce_capacity.usable``), so the two pages
never disagree.

A pool's servers are named by its InfraEnv's agentLabels (``Pool``, ADR-0057's
3.54.0 amendment): ``ocp-<flavor>-<size>-<site>-``, the add-server workflow's
pool draw. The pools are the MCE's own InfraEnvs, labels and all, when it is
read; without it (live status off, or the hub unreadable) they are the ones
the MCE's day1 cluster files name (``nodepool[].infraEnvName``), whose
servers' names are unknown. An available server is in the one pool that
names it; when none or several do (one flavor and size in several zones: the
zone is in no server's name), a held lock on this MCE names its InfraEnv;
otherwise it is counted under none, not guessed.

A named install may pick any ``AVAILABLE`` server: the workflow does not match
a named server to the pool. A pool's list is the free servers it names, or
every free server when its names are unknown. The workflow fails a named run
on a server that is locked, in maintenance or contested (a FAILED run, not a
refusal at the start): its safety refusals, which nothing waives, so those
are shown with why and not offered.

The offered ones are **ready** or **need a fix** (ADR-0057's 3.38.0
amendment). Ready: a pool draw could pick it, as the workflow asks
server-scan (``HEALTHY`` and reachable). Needs a fix: server-scan's health
is not ``HEALTHY``, or it cannot reach the BMC; a pool draw never picks it,
and a named install takes it only with the workflow's ``allow_unhealthy``.
Wingman reads only the row: the workflow also checks the NICs' links and
rechecks the server live, so a ready server's run may still be refused.
A pool's **total** is its available Agents, its ready servers and those that
need a fix: what it reaches once every one is fixed and installed. A pool
whose servers' names are unknown counts none ready or needing a fix.

A **used** Agent (``used_agents``: it carries herzi's
``redbull.io/ever-installed``, or the deployment's excluded labels, and is
bound to nothing) is in server-scan's ``INSTALLED_TO_INVENTORY`` like an
available one, but no NodePool that excludes the label takes it and herzi
removes it from the MCE: it is counted apart, in its InfraEnv label's pool,
and never as available or in a total. Its row is found as the nodes view
finds an Agent's server; one server-scan has no row for is still counted.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from wingman_day1.domain.infra_env_pools import Pool
from wingman_day1.domain.mce_capacity import SPARE_STATE, usable
from wingman_day1.domain.servers import ServerRow
from wingman_day1.domain.used_agents import UsedAgent

AVAILABLE_STATE: Final = "AVAILABLE"
"""server-scan's ``openshift_state`` of a server in no MCE: one the workflow may install."""
INSTALLED_STATE: Final = "INSTALLED"
DRAW_HEALTH: Final = "HEALTHY"
"""The only health a pool draw asks server-scan for."""
UNREACHABLE: Final = "BMC unreachable"
"""server-scan cannot reach the server's BMC: the workflow's ``bmc-reachable`` check."""
FROM_MCE: Final = "mce"
"""The pools are the MCE's own InfraEnv list (live status), with their agentLabels."""
FROM_DAY1: Final = "day1"
"""The pools are the InfraEnvs the MCE's day1 cluster files name: its own list is unknown."""


def infra_env_of(row: ServerRow, mce: str, pools: Iterable[Pool]) -> str | None:
    """The InfraEnv a server belongs to on ``mce``; ``None`` when nothing says which."""
    naming = [pool.infra_env for pool in pools if pool.names(row.name)]
    if len(naming) == 1:
        return naming[0]
    if row.reserved_for_mce == mce and row.reserved_for_infra_env:
        return row.reserved_for_infra_env
    return None


def why_not(row: ServerRow) -> str | None:
    """Why a named install would fail on this ``AVAILABLE`` server, by the first that applies."""
    if row.reserved_by is not None:
        until = f" until {row.reserved_until.isoformat()}" if row.reserved_until else ""
        return f"locked by {row.reserved_by}{until}"
    if row.maintenance:
        return "in maintenance"
    if row.contested:
        return "contested: two clusters claim it"
    return None


def health_problems(row: ServerRow) -> tuple[str, ...]:
    """Why a pool draw would not pick this server, by its own condition in server-scan's row.

    The health checks ``allow_unhealthy`` waives that the row shows: its health
    tier (``health CRITICAL``) and its BMC's reachability. Empty: healthy.
    """
    problems: list[str] = []
    if row.health != DRAW_HEALTH:
        problems.append(f"health {row.health}")
    if not row.reachable:
        problems.append(UNREACHABLE)
    return tuple(problems)


def drawable(row: ServerRow) -> bool:
    """Whether a pool draw could pick this ``AVAILABLE`` server (ready): server-scan's view only."""
    return why_not(row) is None and not health_problems(row)


@dataclass(frozen=True, slots=True)
class HardwareCount:
    """Available servers of one vendor and model."""

    vendor: str | None
    model: str | None
    available: int
    usable: int


@dataclass(frozen=True, slots=True)
class PoolCount:
    """One InfraEnv pool of an MCE (or ``None``: available servers matched to no one InfraEnv)."""

    infra_env: str | None
    available: int
    usable: int
    hardware: tuple[HardwareCount, ...]
    ready: int | None
    """``AVAILABLE`` servers a pool draw could pick; ``None``: its servers' names are unknown."""
    needs_fix: int | None
    """Offered ``AVAILABLE`` servers a pool draw would not pick: unhealthy or unreachable."""
    server_prefix: str | None = None
    """``ocp-<flavor>-<size>-<site>-`` from its agentLabels; ``None`` when unknown."""
    label_problems: tuple[str, ...] = ()
    """Why its agentLabels name no servers: the workflow refuses a pool draw into it."""
    used: tuple[str, ...] = ()
    """Its used Agents' servers, by name: herzi removes them; never available."""

    @property
    def total(self) -> int:
        """Available, ready and needing a fix: what the pool reaches once all are installed."""
        return self.available + (self.ready or 0) + (self.needs_fix or 0)


@dataclass(frozen=True, slots=True)
class MceInventory:
    """One MCE's servers in server-scan, and its pools."""

    site: str
    mce: str
    known: bool
    """server-scan names at least one server on it; ``False``: its counts are unknown, not 0."""
    servers: int
    in_clusters: int
    available: int
    usable: int
    pools: tuple[PoolCount, ...]
    infra_envs: tuple[str, ...]
    infra_envs_error: str | None = None
    """Why the MCE's own InfraEnv list is unknown, when it is."""
    infra_envs_from: str = FROM_MCE
    """Where ``infra_envs`` come from: ``mce`` (its own list) or ``day1`` (its cluster files)."""
    ready: int = 0
    """Free servers its pools name that a draw could pick, each counted once."""
    needs_fix: int = 0
    """Offered free servers its pools name that need a fix, each counted once."""
    used: tuple[UsedAgent, ...] | None = None
    """Its used Agents, herzi's to remove; ``None`` when they were not read."""
    used_error: str | None = None
    """Why its used Agents are unknown, when they could not be read."""

    @property
    def total(self) -> int:
        """Available, ready and needing a fix: what the MCE reaches once all are installed."""
        return self.available + self.ready + self.needs_fix


def _hardware(rows: Sequence[ServerRow]) -> tuple[HardwareCount, ...]:
    counts = Counter((row.vendor, row.model) for row in rows)
    fit = Counter((row.vendor, row.model) for row in rows if usable(row))
    keys = sorted(counts, key=lambda key: (key[0] or "", key[1] or ""))
    return tuple(HardwareCount(v, m, counts[(v, m)], fit[(v, m)]) for v, m in keys)


def _split(free: Sequence[ServerRow], pools: Sequence[Pool]) -> tuple[int, int]:
    """How many offered free servers any of ``pools`` names are ready, and need a fix."""
    named = [r for r in free if why_not(r) is None and any(p.names(r.name) for p in pools)]
    ready = sum(1 for row in named if not health_problems(row))
    return ready, len(named) - ready


def _pool(
    pool: Pool | None,
    rows: Sequence[ServerRow],
    free: Sequence[ServerRow],
    used: Sequence[UsedAgent] = (),
) -> PoolCount:
    """One pool's counts; ``None``: the available servers no one pool names."""
    split = _split(free, [pool]) if pool is not None and pool.server_prefix else None
    return PoolCount(
        infra_env=pool.infra_env if pool else None,
        available=len(rows),
        usable=sum(1 for row in rows if usable(row)),
        hardware=_hardware(rows),
        ready=split[0] if split else None,
        needs_fix=split[1] if split else None,
        server_prefix=pool.server_prefix if pool else None,
        label_problems=pool.label_problems if pool else (),
        used=tuple(u.server for u in used),
    )


def mce_inventory(
    site: str,
    mce: str,
    rows: Sequence[ServerRow],
    *,
    pools: Sequence[Pool],
    infra_envs_error: str | None = None,
    infra_envs_from: str = FROM_MCE,
    used: Sequence[UsedAgent] | None = None,
    used_error: str | None = None,
) -> MceInventory:
    """``mce``'s counts from the whole fleet's ``rows`` and its pools (empty when unknown).

    ``used`` are its used Agents (``None``: not read), their rows left out of
    the available ones.
    """
    on_mce = [row for row in rows if row.mce == mce]
    taken = {u.row.id for u in used or () if u.row is not None}
    available = [row for row in on_mce if row.state == SPARE_STATE and row.id not in taken]
    known = {pool.infra_env: pool for pool in pools}
    by_pool: dict[str | None, list[ServerRow]] = {name: [] for name in known}
    for row in available:
        by_pool.setdefault(infra_env_of(row, mce, pools), []).append(row)
    used_by: dict[str | None, list[UsedAgent]] = {}
    for agent in used or ():
        used_by.setdefault(agent.infra_env, []).append(agent)
        by_pool.setdefault(agent.infra_env, [])
    free = [row for row in rows if row.state == AVAILABLE_STATE]
    names = sorted(name for name in by_pool if name is not None)
    counted = [
        _pool(known.get(name, Pool.unread(name)), by_pool[name], free, used_by.get(name, ()))
        for name in names
    ]
    if by_pool.get(None) or used_by.get(None):
        counted.append(_pool(None, by_pool.get(None, []), free, used_by.get(None, ())))
    ready, needs_fix = _split(free, pools)
    return MceInventory(
        site=site,
        mce=mce,
        known=bool(on_mce),
        servers=len(on_mce),
        in_clusters=sum(1 for row in on_mce if row.state == INSTALLED_STATE),
        available=len(available),
        usable=sum(1 for row in available if usable(row)),
        pools=tuple(counted),
        infra_envs=tuple(sorted(known)),
        infra_envs_error=infra_envs_error,
        infra_envs_from=infra_envs_from,
        ready=ready,
        needs_fix=needs_fix,
        used=tuple(used) if used is not None else None,
        used_error=used_error,
    )


@dataclass(frozen=True, slots=True)
class Candidate:
    """An ``AVAILABLE`` server a pool lists, and why a named install would fail on it."""

    row: ServerRow
    why_not: str | None

    @property
    def offered(self) -> bool:
        """Whether a named install may pick it: no safety refusal."""
        return self.why_not is None

    @property
    def health_problems(self) -> tuple[str, ...]:
        """Why a pool draw would not pick it, by its own condition; empty when healthy."""
        return health_problems(self.row)

    @property
    def ready(self) -> bool:
        """Offered and healthy: a pool draw could pick it. Offered and not ready: it needs a fix."""
        return self.offered and not self.health_problems


def candidates(rows: Iterable[ServerRow], pool: Pool) -> list[Candidate]:
    """A pool's free servers: the ready ones, those that need a fix, the rest; then by name.

    The free servers the pool names, or every free server when its names are unknown.
    """
    found = [
        Candidate(row, why_not(row))
        for row in rows
        if row.state == AVAILABLE_STATE and (pool.server_prefix is None or pool.names(row.name))
    ]
    return sorted(found, key=lambda c: (not c.offered, not c.ready, c.row.name))


def named_refusals(names: Sequence[str], rows: Iterable[ServerRow]) -> list[str]:
    """Why each named server cannot be offered for a named install; empty when all can."""
    by_name = {row.name.casefold(): row for row in rows}
    problems: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = name.casefold()
        if key in seen:
            problems.append(f"{name}: named twice")
            continue
        seen.add(key)
        row = by_name.get(key)
        if row is None:
            problems.append(f"{name}: server-scan has no such server")
        elif row.state != AVAILABLE_STATE:
            problems.append(f"{row.name}: {row.state}, not AVAILABLE")
        elif (reason := why_not(row)) is not None:
            problems.append(f"{row.name}: {reason}")
    return problems
