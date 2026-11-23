"""The top bar's systems, part of the composition root (ADR-0047, ADR-0048; 2026-11-23).

segments-manager and server-scan are listed when day1 has them (their
adapters: real, or the fake fleet's), each with its own UI's address and
whether its area is on (``DAY1_SEGMENTS_AREA``, ``DAY1_SERVER_SCAN_AREA``).
Kept apart so ``main`` stays one screen of wiring per system.
"""

from __future__ import annotations

from wingman_day1.domain.platforms import Platforms
from wingman_day1.domain.platforms import platforms as listed
from wingman_day1.integrations.segments_manager.compose import segments_manager_ui
from wingman_day1.integrations.segments_manager.ports import SegmentLedger
from wingman_day1.integrations.server_scan.compose import server_scan_ui
from wingman_day1.integrations.server_scan.ports import ServerInventory
from wingman_day1.settings import Day1Settings


def platforms(
    settings: Day1Settings, *, ledger: SegmentLedger | None, inventory: ServerInventory | None
) -> Platforms:
    """Each system day1 has an adapter for, where its UI is, and whether its area is on."""
    return listed(
        segments_url=segments_manager_ui(settings) if ledger is not None else None,
        server_scan_url=server_scan_ui(settings) if inventory is not None else None,
        segments_area=settings.day1_segments_area,
        server_scan_area=settings.day1_server_scan_area,
    )
