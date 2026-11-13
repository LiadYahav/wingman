"""The Segments area: segments-manager's sites, statistics and segments (ADR-0047).

segments-manager is the platform's ledger of VLAN segments
(``docs/ecosystem/notes/segments-manager.md``). Its GET answers carry no
schema, so Wingman types them here. The area only reads: nothing is ever
written to segments-manager, and allocation and release stay the workflows'.

A segment's holders are joined to the day1 repo: a holder whose cluster file
is there is a hosted cluster Wingman can link to; any other (an MCE, a UPI
cluster, a name day1 does not have) is only a name.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from wingman_day1.domain.network import SegmentRecord
from wingman_day1.domain.paths import ClusterRef

SEGMENT_TYPES: Final = ("HC", "MCE", "INVENTORY", "PXE", "UPI", "HUB")
"""Every type segments-manager allocates as, in its display order (its ``DISPLAY_TYPES``)."""
STATUSES: Final = ("Available", "Allocated")
"""segments-manager's two states."""


@dataclass(frozen=True, slots=True)
class SegmentQuery:
    """segments-manager's own filters on ``GET /api/segments``; ``None`` is no filter."""

    site: str | None = None
    status: str | None = None
    type: str | None = None


ALL_SEGMENTS: Final = SegmentQuery()
"""No filter: every segment."""


@dataclass(frozen=True, slots=True)
class TypeCount:
    """How many of a site's segments are allocated as one type."""

    type: str
    allocated: int


@dataclass(frozen=True, slots=True)
class SiteStats:
    """One site's card: allocated out of total, and the allocated count per type."""

    site: str
    total_segments: int
    allocated: int
    by_type: tuple[TypeCount, ...]


@dataclass(frozen=True, slots=True)
class SegmentList:
    """``GET /api/segments``: the records read, and those that could not be."""

    records: tuple[SegmentRecord, ...]
    unreadable: tuple[str, ...] = ()
    """One sentence per record segments-manager sent that Wingman could not read."""


@dataclass(frozen=True, slots=True)
class Holder:
    """One name a segment is allocated to; ``ref`` is its cluster file in day1, if it has one."""

    name: str
    ref: ClusterRef | None


@dataclass(frozen=True, slots=True)
class SegmentRow:
    """A segment as the area shows it: segments-manager's record and who holds it."""

    record: SegmentRecord
    holders: tuple[Holder, ...]


@dataclass(frozen=True, slots=True)
class SegmentsView:
    """``GET /api/day1/segments``."""

    rows: tuple[SegmentRow, ...]
    unreadable: tuple[str, ...] = ()
    clusters_error: str | None = None
    """Why the day1 repo's cluster files could not be read: every holder is then unlinked."""
    fresh: bool = False
    """``True`` when segments-manager's database was read just now (``fresh=true`` honoured)."""


def holder_names(holder: str | Sequence[str] | None) -> tuple[str, ...]:
    """``cluster_name`` as names: one, a shared ``UPI`` segment's list, or none while Available."""
    if holder is None:
        return ()
    if isinstance(holder, str):
        return (holder,)
    return tuple(holder)


def refs_by_stem(refs: Iterable[ClusterRef]) -> dict[str, tuple[ClusterRef, ...]]:
    """The day1 repo's cluster files by file stem (two MCEs may hold files of one stem)."""
    found: dict[str, list[ClusterRef]] = {}
    for ref in refs:
        found.setdefault(ref.name, []).append(ref)
    return {name: tuple(where) for name, where in found.items()}


def holders_of(
    record: SegmentRecord, refs: Mapping[str, Sequence[ClusterRef]]
) -> tuple[Holder, ...]:
    """The record's holders, each linked to its cluster file when exactly one file has its stem.

    segments-manager's ``cluster_name`` is the cluster file's stem (ADR-0014,
    ADR-0039). A name no file has, or one two files share, is only a name.
    """
    holders: list[Holder] = []
    for name in holder_names(record.cluster_name):
        where = refs.get(name, ())
        holders.append(Holder(name, where[0] if len(where) == 1 else None))
    return tuple(holders)


def unlinked(record: SegmentRecord) -> SegmentRow:
    """The record with its holders as names only (the day1 repo could not be read)."""
    return SegmentRow(record, tuple(Holder(n, None) for n in holder_names(record.cluster_name)))
