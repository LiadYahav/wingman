"""Inventory Management: each MCE's servers and pools, as server-scan counts them (ADR-0057).

server-scan's ``openshift_state`` says where a server is: ``AVAILABLE`` (in no
MCE), ``INSTALLED_TO_INVENTORY`` (an Agent in its MCE's inventory, in no
cluster: **available**) or ``INSTALLED`` (in a cluster). An available server
is *usable* by placement's rule (``mce_capacity.usable``), so the two pages
never disagree.

A server's InfraEnv is the one whose ``ocp-<infraEnv>`` starts its name: the
add-server workflow draws a pool's servers with ``^ocp-<infraEnv>``, case as
given. The InfraEnvs are the MCE's own list when it is read; without it
(live status off, or the hub unreadable) they are the ones the MCE's day1
cluster files name (``nodepool[].infraEnvName``). When none matches, a held
lock on this MCE names it; otherwise it has none, and is counted under none.

A named install may pick an ``AVAILABLE`` server named ``ocp-<infraEnv>…``.
The workflow fails a named run on a server that is locked, in maintenance or
contested (a FAILED run, not a refusal at the start): its safety refusals,
which nothing waives, so those are shown with why and not offered.

The offered ones are **ready** or **need a fix** (ADR-0057's 3.38.0
amendment). Ready: a pool draw could pick it, as the workflow asks
server-scan (``HEALTHY`` and reachable). Needs a fix: server-scan's health
is not ``HEALTHY``, or it cannot reach the BMC; a pool draw never picks it,
and a named install takes it only with the workflow's ``allow_unhealthy``.
Wingman reads only the row: the workflow also checks the NICs' links and
rechecks the server live, so a ready server's run may still be refused.
A pool's **total** is its available Agents, its ready servers and those that
need a fix: what it reaches once every one is fixed and installed.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from wingman_day1.domain.mce_capacity import SPARE_STATE, usable
from wingman_day1.domain.servers import ServerRow

AVAILABLE_STATE: Final = "AVAILABLE"
"""server-scan's ``openshift_state`` of a server in no MCE: one the workflow may install."""
INSTALLED_STATE: Final = "INSTALLED"
NAME_PREFIX: Final = "ocp-"
"""A pool's servers are named ``ocp-<infraEnv>…`` (the workflow's draw pattern)."""
DRAW_HEALTH: Final = "HEALTHY"
"""The only health a pool draw asks server-scan for."""
UNREACHABLE: Final = "BMC unreachable"
"""server-scan cannot reach the server's BMC: the workflow's ``bmc-reachable`` check."""
FROM_MCE: Final = "mce"
"""The pools are the MCE's own InfraEnv list (live status)."""
FROM_DAY1: Final = "day1"
"""The pools are the InfraEnvs the MCE's day1 cluster files name: its own list is unknown."""


def named_for(name: str, infra_env: str) -> bool:
    """Whether a server's name puts it in ``infra_env``'s pool (``^ocp-<infraEnv>``)."""
    return name.startswith(f"{NAME_PREFIX}{infra_env}")


def infra_env_of(row: ServerRow, mce: str, infra_envs: Iterable[str]) -> str | None:
    """The InfraEnv a server belongs to on ``mce``; ``None`` when nothing says."""
    matching = [infra_env for infra_env in infra_envs if named_for(row.name, infra_env)]
    if matching:
        return max(matching, key=len)
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
    """One InfraEnv pool of an MCE (or ``None``: available servers matched to no InfraEnv)."""

    infra_env: str | None
    available: int
    usable: int
    hardware: tuple[HardwareCount, ...]
    ready: int | None
    """``AVAILABLE`` servers a pool draw could pick; ``None`` without an InfraEnv."""
    needs_fix: int | None
    """Offered ``AVAILABLE`` servers a pool draw would not pick: unhealthy or unreachable."""

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
    """Free servers named for any of its pools that a draw could pick, each counted once."""
    needs_fix: int = 0
    """Offered free servers named for any of its pools that need a fix, each counted once."""

    @property
    def total(self) -> int:
        """Available, ready and needing a fix: what the MCE reaches once all are installed."""
        return self.available + self.ready + self.needs_fix


def _hardware(rows: Sequence[ServerRow]) -> tuple[HardwareCount, ...]:
    counts = Counter((row.vendor, row.model) for row in rows)
    fit = Counter((row.vendor, row.model) for row in rows if usable(row))
    keys = sorted(counts, key=lambda key: (key[0] or "", key[1] or ""))
    return tuple(HardwareCount(v, m, counts[(v, m)], fit[(v, m)]) for v, m in keys)


def _split(free: Sequence[ServerRow], pools: Sequence[str]) -> tuple[int, int]:
    """How many offered free servers named for any of ``pools`` are ready, and need a fix."""
    named = [r for r in free if why_not(r) is None and any(named_for(r.name, p) for p in pools)]
    ready = sum(1 for row in named if not health_problems(row))
    return ready, len(named) - ready


def _pool(infra_env: str | None, rows: Sequence[ServerRow], free: Sequence[ServerRow]) -> PoolCount:
    ready, needs_fix = _split(free, [infra_env]) if infra_env is not None else (None, None)
    return PoolCount(
        infra_env=infra_env,
        available=len(rows),
        usable=sum(1 for row in rows if usable(row)),
        hardware=_hardware(rows),
        ready=ready,
        needs_fix=needs_fix,
    )


def mce_inventory(
    site: str,
    mce: str,
    rows: Sequence[ServerRow],
    *,
    infra_envs: Sequence[str],
    infra_envs_error: str | None = None,
    infra_envs_from: str = FROM_MCE,
) -> MceInventory:
    """``mce``'s counts from the whole fleet's ``rows`` and its InfraEnvs (empty when unknown)."""
    on_mce = [row for row in rows if row.mce == mce]
    available = [row for row in on_mce if row.state == SPARE_STATE]
    by_pool: dict[str | None, list[ServerRow]] = {name: [] for name in infra_envs}
    for row in available:
        by_pool.setdefault(infra_env_of(row, mce, infra_envs), []).append(row)
    free = [row for row in rows if row.state == AVAILABLE_STATE]
    names = sorted(name for name in by_pool if name is not None)
    pools = [_pool(name, by_pool[name], free) for name in names]
    if by_pool.get(None):
        pools.append(_pool(None, by_pool[None], free))
    ready, needs_fix = _split(free, names)
    return MceInventory(
        site=site,
        mce=mce,
        known=bool(on_mce),
        servers=len(on_mce),
        in_clusters=sum(1 for row in on_mce if row.state == INSTALLED_STATE),
        available=len(available),
        usable=sum(1 for row in available if usable(row)),
        pools=tuple(pools),
        infra_envs=tuple(sorted(infra_envs)),
        infra_envs_error=infra_envs_error,
        infra_envs_from=infra_envs_from,
        ready=ready,
        needs_fix=needs_fix,
    )


@dataclass(frozen=True, slots=True)
class Candidate:
    """An ``AVAILABLE`` server named for a pool, and why a named install would fail on it."""

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


def candidates(rows: Iterable[ServerRow], infra_env: str) -> list[Candidate]:
    """A pool's free servers: the ready ones, those that need a fix, the rest; then by name."""
    found = [
        Candidate(row, why_not(row))
        for row in rows
        if row.state == AVAILABLE_STATE and named_for(row.name, infra_env)
    ]
    return sorted(found, key=lambda c: (not c.offered, not c.ready, c.row.name))


def named_refusals(names: Sequence[str], rows: Iterable[ServerRow], infra_env: str) -> list[str]:
    """Why each named server cannot be offered for ``infra_env``; empty when all can."""
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
        elif not named_for(row.name, infra_env):
            problems.append(f"{row.name}: not named {NAME_PREFIX}{infra_env}…")
        elif (reason := why_not(row)) is not None:
            problems.append(f"{row.name}: {reason}")
    return problems
