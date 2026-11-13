"""CachedSegmentLedger: segments-manager's answers, cached per replica.

The cluster page reads its cluster's segment on every visit, and the Segments
area re-reads the sites, statistics and segments every 30 seconds while it is
open; segments-manager has no webhook to day1, so each answer expires with the
TTL (ADR-0011, ADR-0039, ADR-0047). "No such segment" is an answer and is
cached like a record; a failure is not.

A ``fresh`` read (the area's Refresh button) drops everything cached from
segments-manager, the cluster page's segments too, and keeps what it reads.
"""

from __future__ import annotations

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.network import SegmentRecord
from wingman_day1.domain.segments import ALL_SEGMENTS, SegmentList, SegmentQuery, SiteStats
from wingman_day1.infrastructure import cache_keys as keys
from wingman_day1.ports import SegmentLedger


class CachedSegmentLedger:
    """A ``SegmentLedger`` that caches ``inner``'s answers."""

    def __init__(self, inner: SegmentLedger, cache: TtlCache, *, ttl: float) -> None:
        """Cache ``inner``'s answers in ``cache`` for ``ttl`` seconds."""
        self._inner = inner
        self._cache = cache
        self._ttl = ttl

    async def segment(self, cidr: str) -> SegmentRecord | None:
        """See SegmentLedger.segment."""
        return await self._cache.get_or_fetch(
            keys.segment(cidr), lambda: self._inner.segment(cidr), ttl=self._ttl
        )

    async def sites(self) -> tuple[str, ...]:
        """See SegmentLedger.sites."""
        return await self._cache.get_or_fetch(
            keys.segment_sites(), self._inner.sites, ttl=self._ttl
        )

    async def stats(self) -> tuple[SiteStats, ...]:
        """See SegmentLedger.stats."""
        return await self._cache.get_or_fetch(
            keys.segment_stats(), self._inner.stats, ttl=self._ttl
        )

    async def segments(
        self, query: SegmentQuery = ALL_SEGMENTS, *, fresh: bool = False
    ) -> SegmentList:
        """See SegmentLedger.segments; ``fresh`` first forgets every segments-manager answer."""
        if fresh:
            self._cache.invalidate_prefix(keys.segments_manager_prefix())
        return await self._cache.get_or_fetch(
            keys.segment_list(query.site, query.status, query.type),
            lambda: self._inner.segments(query, fresh=fresh),
            ttl=self._ttl,
        )
