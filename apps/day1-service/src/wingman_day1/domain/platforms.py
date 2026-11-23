"""The systems beside Wingman in an admin's top bar: segments-manager and server-scan.

The team keeps both apart from Wingman (ADR-0066): the top bar links to each
one's own UI, in a new tab. A system Wingman is not configured for, or whose
UI it knows no address for, is not listed. Wingman only links to them here:
it never calls a UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PlatformId = Literal["segments", "server-scan"]


@dataclass(frozen=True, slots=True)
class Platform:
    """One system: the top bar's link to it."""

    id: PlatformId
    """The web's key for it."""
    name: str
    """Its own name, as its UI says it."""
    url: str
    """Its own UI, for people's browsers."""


def platforms(*, segments_url: str | None, server_scan_url: str | None) -> tuple[Platform, ...]:
    """Each system whose UI's address is known (``None`` or "": none), in the top bar's order."""
    entries = (
        Platform("segments", "Segments Manager", segments_url or ""),
        Platform("server-scan", "Server Scan", server_scan_url or ""),
    )
    return tuple(entry for entry in entries if entry.url)
