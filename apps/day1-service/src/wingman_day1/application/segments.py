"""The Segments area: segments-manager's sites, statistics and segments (ADR-0047).

Read only. The segments come with their holders joined to the day1 repo's
cluster files (read once per commit and cached, ADR-0035), so a holder that
is a hosted cluster links to Wingman's page, and each row says where
segments-manager disagrees with a cluster file (no further call). The day1
repo failing never fails the page: the segments are listed with every holder
unlinked, no checks, and the reason. segments-manager failing is
``SegmentsManagerUnavailableError``.

A ``fresh`` read (the Refresh button) is honoured at most once per
``FRESH_COOLDOWN_SECONDS`` per replica, so a held button cannot hammer
segments-manager's database; inside that window it is answered from the
cache the last one filled, and says so.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Final

from wingman_core.domain.errors import GitUnavailableError, PermissionDeniedError
from wingman_day1.application.clusters import ClusterFile, ClusterService
from wingman_day1.domain.network import file_network
from wingman_day1.domain.segments import (
    ALL_SEGMENTS,
    SegmentQuery,
    SegmentRow,
    SegmentsView,
    SiteStats,
    holders_of,
    refs_by_stem,
    unlinked,
    with_mismatches,
)
from wingman_day1.ports import SegmentLedger

FRESH_COOLDOWN_SECONDS: Final = 5.0
"""The shortest time between two reads of segments-manager's database, per replica."""


class SegmentsService:
    """``GET /api/day1/segments``, ``/sites`` and ``/stats``."""

    def __init__(
        self,
        ledger: SegmentLedger,
        clusters: ClusterService,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Read through ``ledger`` (cached); join holders to ``clusters``' files."""
        self._ledger = ledger
        self._clusters = clusters
        self._clock = clock
        self._last_fresh: float | None = None

    async def sites(self) -> tuple[str, ...]:
        """segments-manager's sites, in its order."""
        return await self._ledger.sites()

    async def stats(self) -> tuple[SiteStats, ...]:
        """Each site's allocated and total segments, and allocated per type."""
        return await self._ledger.stats()

    async def segments(
        self, query: SegmentQuery = ALL_SEGMENTS, *, fresh: bool = False
    ) -> SegmentsView:
        """The segments ``query`` matches, each with its holders; ``fresh`` within the cool-down."""
        fresh = fresh and self._may_read_fresh()
        listing, files = await asyncio.gather(
            self._ledger.segments(query, fresh=fresh), self._cluster_files()
        )
        if isinstance(files, str):
            rows = tuple(unlinked(record) for record in listing.records)
            return SegmentsView(rows, listing.unreadable, clusters_error=files, fresh=fresh)
        refs = refs_by_stem(file.ref for file in files)
        rows = tuple(SegmentRow(r, holders_of(r, refs)) for r in listing.records)
        networks = {
            f.ref: file_network(f.values.vlan_id, f.values.dhcp_network)
            for f in files
            if f.values is not None
        }
        return SegmentsView(with_mismatches(rows, networks), listing.unreadable, fresh=fresh)

    def _may_read_fresh(self) -> bool:
        """Whether a fresh read is allowed now; taking it starts the next cool-down."""
        now = self._clock()
        if self._last_fresh is not None and now - self._last_fresh < FRESH_COOLDOWN_SECONDS:
            return False
        self._last_fresh = now
        return True

    async def _cluster_files(self) -> list[ClusterFile] | str:
        """The day1 repo's cluster files, or why they could not be read."""
        try:
            return await self._clusters.clusters()
        except (GitUnavailableError, PermissionDeniedError) as exc:
            return f"{type(exc).__name__.removesuffix('Error')}: {exc}"
