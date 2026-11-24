"""The Infrastructure sidebar's systems, part of the composition root (ADR-0066, ADR-0067).

segments-manager and server-scan are listed when day1 has them (their
adapters: real, or the fake fleet's), each with its own UI's address. Kept
apart so ``main`` stays one screen of wiring per system.
"""

from __future__ import annotations

from wingman_day1.domain.platforms import Platform
from wingman_day1.domain.platforms import platforms as listed
from wingman_day1.integrations.segments_manager.compose import segments_manager_ui
from wingman_day1.integrations.segments_manager.ports import SegmentLedger
from wingman_day1.integrations.server_scan.compose import server_scan_ui
from wingman_day1.integrations.server_scan.ports import ServerInventory
from wingman_day1.settings import Day1Settings


def platforms(
    settings: Day1Settings, *, ledger: SegmentLedger | None, inventory: ServerInventory | None
) -> tuple[Platform, ...]:
    """Each system day1 has an adapter for, and where its UI is."""
    return listed(
        segments_url=segments_manager_ui(settings) if ledger is not None else None,
        server_scan_url=server_scan_ui(settings) if inventory is not None else None,
    )
