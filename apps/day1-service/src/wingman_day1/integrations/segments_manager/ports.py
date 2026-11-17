"""segments-manager's port: the one way day1 reads it (ADR-0039, ADR-0047).

A cluster's network check (the EPG) and the Segments area both read
segments-manager through this port and its one adapter, cache and fake.
Nothing is ever written to it.
"""

from __future__ import annotations

from typing import Protocol

from wingman_day1.domain.network import SegmentRecord
from wingman_day1.integrations.segments_manager.domain.segments import (
    ALL_SEGMENTS,
    SegmentList,
    SegmentQuery,
    SiteStats,
)


class SegmentLedger(Protocol):
    """segments-manager: the platform's ledger of VLAN segments (read only, ADR-0039).

    Raises ``SegmentsManagerUnavailableError`` when segments-manager cannot
    answer: the EPG is then unknown, never "none". Nothing is ever written to it.
    """

    async def segment(self, cidr: str) -> SegmentRecord | None:
        """The segment ``cidr`` (``a.b.c.0/24``); ``None`` when segments-manager has no such one."""
        ...

    async def sites(self) -> tuple[str, ...]:
        """Its sites (``GET /api/sites``), in its order (ADR-0047)."""
        ...

    async def stats(self) -> tuple[SiteStats, ...]:
        """Each site's allocated and total segments, and allocated per type (``GET /api/stats``)."""
        ...

    async def segments(
        self, query: SegmentQuery = ALL_SEGMENTS, *, fresh: bool = False
    ) -> SegmentList:
        """The segments ``query`` matches (``GET /api/segments``).

        ``fresh`` asks segments-manager to read its database, not its 60-second cache.
        """
        ...
