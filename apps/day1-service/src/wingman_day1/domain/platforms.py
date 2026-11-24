"""The systems beside Wingman in Infrastructure's sidebar: segments-manager and server-scan.

The team keeps both apart from Wingman (ADR-0066): the Infrastructure
workspace's sidebar links to each one's own UI, in a new tab, under the name
given here (ADR-0067; the top bar until 3.57.0). A system Wingman is not
configured for, or whose UI it knows no address for, is not listed. Wingman
only links to them here: it never calls a UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PlatformId = Literal["segments", "server-scan"]


@dataclass(frozen=True, slots=True)
class Platform:
    """One system: the sidebar's link to it."""

    id: PlatformId
    """The web's key for it."""
    name: str
    """Its own name, as its UI says it: the link's label (the web keeps no word of its own)."""
    url: str
    """Its own UI, for people's browsers."""


def platforms(*, segments_url: str | None, server_scan_url: str | None) -> tuple[Platform, ...]:
    """Each system whose UI's address is known (``None`` or "": none), in the sidebar's order."""
    entries = (
        Platform("segments", "Segments Manager", segments_url or ""),
        Platform("server-scan", "Server Scan", server_scan_url or ""),
    )
    return tuple(entry for entry in entries if entry.url)
