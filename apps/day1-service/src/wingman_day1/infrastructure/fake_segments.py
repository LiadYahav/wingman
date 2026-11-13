"""FakeSegmentLedger: segments-manager in memory (ADR-0039, ADR-0047).

Tests seed it directly; ``DAY1_FAKE_FLEET=true`` (development only) seeds it
from ``dev/fleet-fixtures/segments.yaml``, written in segments-manager's own
shape and read by the HTTP adapter's parser. It answers as segments-manager
does: its sites are the fixture's ``sites`` (its ``SITE_NETWORKS`` keys, so a
site may have no segments), else the records' sites; its statistics are
counted from the records, every site and every type listed; its filters
compare without case, and a type never matches an Available segment (it has
none). It raises the same error as the real adapter.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Final

import yaml

from wingman_day1.domain.errors import SegmentsManagerUnavailableError
from wingman_day1.domain.network import ALLOCATED, SegmentRecord
from wingman_day1.domain.segments import (
    ALL_SEGMENTS,
    SEGMENT_TYPES,
    SegmentList,
    SegmentQuery,
    SiteStats,
    TypeCount,
)
from wingman_day1.infrastructure.segments_manager_parse import segment_record

SEGMENTS_FILE: Final = Path("dev/fleet-fixtures/segments.yaml")


class FakeSegmentLedger:
    """A ``SegmentLedger`` over seeded records; ``unavailable`` fails every read, as if down."""

    def __init__(
        self,
        records: Iterable[SegmentRecord] = (),
        *,
        sites: Sequence[str] | None = None,
        unavailable: bool = False,
    ) -> None:
        """Seed the ledger; ``sites`` is its site list (default: the records' sites)."""
        self._records = {record.segment: record for record in records}
        self._sites = tuple(sites) if sites is not None else None
        self.unavailable = unavailable
        self.reads = 0
        """How many times ``segment`` was called."""
        self.list_reads = 0
        """How many times ``sites``, ``stats`` or ``segments`` were called."""
        self.fresh_reads = 0
        """How many of the ``segments`` calls were ``fresh``."""

    async def segment(self, cidr: str) -> SegmentRecord | None:
        """See SegmentLedger.segment."""
        self.reads += 1
        self._check(f"reading segment {cidr}")
        return self._records.get(cidr)

    async def sites(self) -> tuple[str, ...]:
        """See SegmentLedger.sites."""
        self.list_reads += 1
        self._check("reading the sites")
        return self._site_list()

    async def stats(self) -> tuple[SiteStats, ...]:
        """See SegmentLedger.stats."""
        self.list_reads += 1
        self._check("reading the statistics")
        return tuple(self._site_stats(site) for site in self._site_list())

    async def segments(
        self, query: SegmentQuery = ALL_SEGMENTS, *, fresh: bool = False
    ) -> SegmentList:
        """See SegmentLedger.segments."""
        self.list_reads += 1
        if fresh:
            self.fresh_reads += 1
        self._check("reading the segments")
        return SegmentList(tuple(r for r in self._records.values() if _matches(r, query)))

    def _check(self, what: str) -> None:
        if self.unavailable:
            raise SegmentsManagerUnavailableError(f"segments-manager answered 503 {what}")

    def _site_list(self) -> tuple[str, ...]:
        if self._sites is not None:
            return self._sites
        return tuple(sorted({r.site for r in self._records.values() if r.site}))

    def _site_stats(self, site: str) -> SiteStats:
        held = [r for r in self._records.values() if r.site == site]
        allocated = [r for r in held if r.status == ALLOCATED]
        return SiteStats(
            site=site,
            total_segments=len(held),
            allocated=len(allocated),
            by_type=tuple(
                TypeCount(kind, sum(1 for r in allocated if r.type == kind))
                for kind in SEGMENT_TYPES
            ),
        )


def _matches(record: SegmentRecord, query: SegmentQuery) -> bool:
    """segments-manager's ``_segment_matches``: every filter given, compared without case."""
    pairs = ((query.site, record.site), (query.status, record.status), (query.type, record.type))
    return all(want is None or (have or "").lower() == want.lower() for want, have in pairs)


def default_segments_file() -> Path:
    """``dev/fleet-fixtures/segments.yaml`` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / SEGMENTS_FILE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{SEGMENTS_FILE} not found above this file")


def _fixture(path: Path) -> tuple[list[object], list[str] | None]:
    """A fixture's ``items``, and its ``sites`` (``None`` when it lists none)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(items := raw.get("items"), list):
        raise TypeError(f"{path}: expected a mapping with an 'items' list")
    sites = raw.get("sites")
    if sites is not None and not (
        isinstance(sites, list) and all(isinstance(s, str) and s for s in sites)
    ):
        raise TypeError(f"{path}: 'sites' must be a list of site names")
    return items, sites


def load_segments(path: Path) -> list[SegmentRecord]:
    """The segments (``items``, in segments-manager's shape) of a fixture."""
    records = [segment_record(item) for item in _fixture(path)[0]]
    segments = [record.segment for record in records]
    if len(set(segments)) != len(segments):
        raise ValueError(f"{path}: a segment is listed twice")
    return records


def load_fake_ledger(path: Path) -> FakeSegmentLedger:
    """A fake ledger from a fixture: its ``items``, and its ``sites`` when it lists them."""
    return FakeSegmentLedger(load_segments(path), sites=_fixture(path)[1])
