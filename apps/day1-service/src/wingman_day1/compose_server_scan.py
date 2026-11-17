"""server-scan's part of the composition root (ADR-0038, ADR-0048).

This builds the HTTP adapter (``platform_adapters`` picks it, none, or the
fake fleet's), puts the one cache in front of it, which the Nodes tab,
placement, Inventory Management and the Server Scan area share, and builds
the area's use case. Kept apart so ``main`` stays one screen of wiring per system.
``server_scan_ui`` is where a person's browser and Claude Code find
server-scan: the node links, and the Claude page's commands and zip.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.application.server_scan import ServerScanService
from wingman_day1.application.server_scan_jobs import ServerScanJobs
from wingman_day1.domain.server_scan_events import audit_detail
from wingman_day1.domain.server_scan_jobs import jobs_detail
from wingman_day1.domain.server_scan_servers import maintenance_detail
from wingman_day1.domain.server_scan_skill import token_line
from wingman_day1.infrastructure.cached_server_scan import CachedServerInventory
from wingman_day1.infrastructure.server_scan import HttpServerInventory
from wingman_day1.ports import ServerInventory
from wingman_day1.settings import Day1Settings

SITES_TTL_SECONDS: Final = 10.0
"""The longest day1 keeps server-scan's sites: server-scan caches them 30 seconds itself."""
SKILL_TTL_SECONDS: Final = 60.0
"""The longest day1 keeps server-scan's skill: its own Claude page reads it every minute."""
FAKE_SERVER_SCAN_UI: Final = "http://server-scan.example"
"""Where the fake fleet's server-scan is said to be when ``SERVER_SCAN_UI_URL`` is empty."""


def http_inventory(
    settings: Day1Settings,
    *,
    metrics: WingmanMetrics,
    closers: list[Callable[[], Awaitable[None]]],
) -> ServerInventory | None:
    """server-scan over HTTP with its three tokens; ``None`` when ``SERVER_SCAN_URL`` is empty."""
    if not settings.server_scan_url:
        return None
    scan = HttpServerInventory(
        base_url=settings.server_scan_url,
        ui_url=settings.server_scan_ui_base,
        token=settings.server_scan_token.get_secret_value(),
        admin_token=settings.server_scan_admin_token.get_secret_value(),
        auditor_token=settings.server_scan_auditor_token.get_secret_value(),
        verify=settings.server_scan_tls_verify,
        timeout_seconds=settings.server_scan_timeout_seconds,
        metrics=metrics,
    )
    closers.append(scan.aclose)
    return scan


def server_scan_ui(settings: Day1Settings) -> str:
    """server-scan's address for people: ``SERVER_SCAN_UI_URL``, its API's, or the fake's."""
    return settings.server_scan_ui_base or FAKE_SERVER_SCAN_UI


DIAGRAM_TTL_SECONDS: Final = 300.0
"""How long day1 keeps one of server-scan's diagrams: they change only with its releases."""


def cached_inventory(
    inventory: ServerInventory | None, cache: TtlCache, *, ttl: float
) -> ServerInventory | None:
    """``inventory`` behind the shared cache: rows for ``ttl``, sites and skill shorter.

    The architecture diagrams are kept five minutes.
    """
    if inventory is None:
        return None
    return CachedServerInventory(
        inventory,
        cache,
        ttl=ttl,
        sites_ttl=min(ttl, SITES_TTL_SECONDS),
        skill_ttl=min(ttl, SKILL_TTL_SECONDS),
        diagram_ttl=DIAGRAM_TTL_SECONDS,
    )


def server_scan_service(
    inventory: ServerInventory | None, settings: Day1Settings
) -> ServerScanService | None:
    """The Server Scan area over the cached ``inventory``; ``None`` without one (501).

    Its maintenance toggle works with server-scan's admin token, or with no
    token at all (a server-scan with auth off); a viewer token alone turns it
    off (ADR-0048's 3.23.0 amendment). A server's History works the same way
    with server-scan's auditor token (3.25.0), and so does the Events page
    (3.31.0). The Claude page names the token line server-scan writes into
    Wingman's copy of its skill (3.27.0). The Jobs page follows the toggle's
    rule, its reads too (3.32.0).
    """
    if inventory is None:
        return None
    viewer = bool(settings.server_scan_token.get_secret_value())
    auditor = bool(settings.server_scan_auditor_token.get_secret_value())
    admin = bool(settings.server_scan_admin_token.get_secret_value())
    return ServerScanService(
        inventory,
        ui_url=server_scan_ui(settings),
        token_line=token_line(viewer_token=viewer),
        maintenance_detail=maintenance_detail(viewer_token=viewer, admin_token=admin),
        jobs=ServerScanJobs(inventory, detail=jobs_detail(viewer_token=viewer, admin_token=admin)),
        history_detail=audit_detail("History", viewer_token=viewer, auditor_token=auditor),
        events_detail=audit_detail("Events", viewer_token=viewer, auditor_token=auditor),
    )
