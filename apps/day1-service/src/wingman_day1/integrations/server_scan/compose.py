"""server-scan's part of the composition root (ADR-0038).

This builds the HTTP adapter (``platform_adapters`` picks it, none, or the
fake fleet's) and puts the one cache in front of it, which the Nodes tab,
placement and Inventory Management share. Kept apart so ``main`` stays one
screen of wiring per system. ``server_scan_ui`` is where a person's browser
finds server-scan: the node links and the Infrastructure sidebar's link.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Final

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.integrations.server_scan.infrastructure.adapter import HttpServerInventory
from wingman_day1.integrations.server_scan.infrastructure.cached import CachedServerInventory
from wingman_day1.integrations.server_scan.ports import ServerInventory
from wingman_day1.settings import Day1Settings

FAKE_SERVER_SCAN_UI: Final = "http://server-scan.example"
"""Where the fake fleet's server-scan is said to be when ``SERVER_SCAN_UI_URL`` is empty."""


def http_inventory(
    settings: Day1Settings,
    *,
    metrics: WingmanMetrics,
    closers: list[Callable[[], Awaitable[None]]],
) -> ServerInventory | None:
    """server-scan over HTTP with its viewer token; ``None`` when ``SERVER_SCAN_URL`` is empty."""
    if not settings.server_scan_url:
        return None
    scan = HttpServerInventory(
        base_url=settings.server_scan_url,
        token=settings.server_scan_token.get_secret_value(),
        verify=settings.server_scan_tls_verify,
        timeout_seconds=settings.server_scan_timeout_seconds,
        metrics=metrics,
    )
    closers.append(scan.aclose)
    return scan


def server_scan_ui(settings: Day1Settings) -> str:
    """server-scan's address for people: ``SERVER_SCAN_UI_URL``, its API's, or the fake's."""
    return settings.server_scan_ui_base or FAKE_SERVER_SCAN_UI


def cached_inventory(
    inventory: ServerInventory | None, cache: TtlCache, *, ttl: float
) -> ServerInventory | None:
    """``inventory`` behind the shared cache, its rows kept ``ttl`` seconds."""
    if inventory is None:
        return None
    return CachedServerInventory(inventory, cache, ttl=ttl)
