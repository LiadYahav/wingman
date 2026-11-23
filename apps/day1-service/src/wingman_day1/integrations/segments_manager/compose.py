"""segments-manager's part of the composition root (ADR-0039, ADR-0047).

``main`` builds the app; this builds what segments-manager feeds: the ledger
(real, none, or the fake fleet's), its cache for a cluster's network check,
the Segments area's use case, and where its UI is for people. Kept apart so
``main`` stays one screen of wiring per system.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.application.clusters import ClusterService
from wingman_day1.integrations.segments_manager.application.segments import SegmentsService
from wingman_day1.integrations.segments_manager.infrastructure.adapter import HttpSegmentLedger
from wingman_day1.integrations.segments_manager.infrastructure.cached import CachedSegmentLedger
from wingman_day1.integrations.segments_manager.ports import SegmentLedger
from wingman_day1.settings import Day1Settings

SEGMENTS_TTL_SECONDS: Final = 10.0
"""The longest the Segments area keeps an answer: the page re-reads every 30 seconds."""
FAKE_SEGMENTS_MANAGER_UI: Final = "http://segments-manager.example"
"""Where the fake fleet's segments-manager links point when no segments-manager URL is set."""


def segments_manager_ui(settings: Day1Settings) -> str:
    """segments-manager's UI for people (the cluster page's and the top bar's links); "": none."""
    fake = FAKE_SEGMENTS_MANAGER_UI if settings.day1_fake_fleet else ""
    return settings.segments_manager_ui_base or fake


def segment_ledger(
    settings: Day1Settings,
    *,
    metrics: WingmanMetrics,
    closers: list[Callable[[], Awaitable[None]]],
) -> SegmentLedger | None:
    """segments-manager, real or none; or, with the fake fleet, its fake (ADR-0039)."""
    if settings.day1_fake_fleet:
        from wingman_day1.integrations.segments_manager.infrastructure.fake import (
            default_segments_file,
            load_fake_ledger,
        )

        return load_fake_ledger(default_segments_file())
    if not settings.segments_manager_url:
        return None
    ledger = HttpSegmentLedger(
        base_url=settings.segments_manager_url,
        verify=settings.segments_manager_tls_verify,
        timeout_seconds=settings.segments_manager_timeout_seconds,
        metrics=metrics,
    )
    closers.append(ledger.aclose)
    return ledger


def network_ledger(
    ledger: SegmentLedger | None, cache: TtlCache, *, ttl: float
) -> SegmentLedger | None:
    """``ledger`` behind day1's cache for a cluster's network check (ADR-0039); ``None`` without."""
    if ledger is None:
        return None
    return CachedSegmentLedger(ledger, cache, ttl=ttl)


def segments_service(
    ledger: SegmentLedger | None, cache: TtlCache, clusters: ClusterService, *, ttl: float
) -> SegmentsService | None:
    """The Segments area over its own short cache of ``ledger``; ``None`` without one (501)."""
    if ledger is None:
        return None
    cached = CachedSegmentLedger(ledger, cache, ttl=min(ttl, SEGMENTS_TTL_SECONDS))
    return SegmentsService(cached, clusters)
