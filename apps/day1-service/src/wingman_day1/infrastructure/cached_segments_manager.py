"""CachedSegmentLedger: segments-manager's answer for one segment, cached per replica.

The cluster page reads its cluster's segment on every visit; segments-manager
has no webhook to day1, so the answer expires with the TTL (ADR-0011,
ADR-0039). "No such segment" is an answer and is cached like a record; a
failure is not.
"""

from __future__ import annotations

from wingman_core.infrastructure.cache import TtlCache
from wingman_day1.domain.network import SegmentRecord
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
