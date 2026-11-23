"""segments-manager's port: the one way day1 reads it (ADR-0039).

A cluster's network check (the EPG) reads segments-manager through this port
and its one adapter, cache and fake. Nothing is ever written to it.
"""

from __future__ import annotations

from typing import Protocol

from wingman_day1.domain.network import SegmentRecord


class SegmentLedger(Protocol):
    """segments-manager: the platform's ledger of VLAN segments (read only, ADR-0039).

    Raises ``SegmentsManagerUnavailableError`` when segments-manager cannot
    answer: the EPG is then unknown, never "none". Nothing is ever written to it.
    """

    async def segment(self, cidr: str) -> SegmentRecord | None:
        """The segment ``cidr`` (``a.b.c.0/24``); ``None`` when segments-manager has no such one."""
        ...
