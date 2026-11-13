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
contested (a FAILED run, not a refusal at the start), so those are shown with
why and not offered. Health is shown, not refused: a named install may waive
it. Everything else is the workflow's to judge.
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


def drawable(row: ServerRow) -> bool:
    """Whether a pool draw could pick this ``AVAILABLE`` server: server-scan's view only."""
    return (
        row.reserved_by is None
        and not row.maintenance
        and row.reachable
        and row.health == DRAW_HEALTH
    )


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
    drawable: int | None
    """``AVAILABLE`` servers a pool draw could pick; ``None`` without an InfraEnv."""


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


def _hardware(rows: Sequence[ServerRow]) -> tuple[HardwareCount, ...]:
    counts = Counter((row.vendor, row.model) for row in rows)
    fit = Counter((row.vendor, row.model) for row in rows if usable(row))
    keys = sorted(counts, key=lambda key: (key[0] or "", key[1] or ""))
    return tuple(HardwareCount(v, m, counts[(v, m)], fit[(v, m)]) for v, m in keys)


def _pool(infra_env: str | None, rows: Sequence[ServerRow], free: Sequence[ServerRow]) -> PoolCount:
    return PoolCount(
        infra_env=infra_env,
        available=len(rows),
        usable=sum(1 for row in rows if usable(row)),
        hardware=_hardware(rows),
        drawable=(
            sum(1 for row in free if named_for(row.name, infra_env) and drawable(row))
            if infra_env is not None
            else None
        ),
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
    )


@dataclass(frozen=True, slots=True)
class Candidate:
    """An ``AVAILABLE`` server named for a pool, and why a named install would fail on it."""

    row: ServerRow
    why_not: str | None

    @property
    def offered(self) -> bool:
        """Whether a named install may pick it."""
        return self.why_not is None


def candidates(rows: Iterable[ServerRow], infra_env: str) -> list[Candidate]:
    """The servers a named install into ``infra_env`` may pick, offered first, then by name."""
    found = [
        Candidate(row, why_not(row))
        for row in rows
        if row.state == AVAILABLE_STATE and named_for(row.name, infra_env)
    ]
    return sorted(found, key=lambda c: (not c.offered, c.row.name))


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
