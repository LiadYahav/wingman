"""The systems beside Wingman in an admin's top bar: segments-manager and server-scan.

The team keeps both apart from Wingman (the 2026-11-23 amendments of ADR-0047
and ADR-0048): the top bar links to each one's own UI, in a new tab, and
Wingman's area for it (the Segments area, the Server Scan area) is off unless
the deployment turns it on (``DAY1_SEGMENTS_AREA``, ``DAY1_SERVER_SCAN_AREA``).
A system Wingman is not configured for is not listed. Wingman only links to
them here: it never calls a UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PlatformId = Literal["segments", "server-scan"]


@dataclass(frozen=True, slots=True)
class Platform:
    """One system: the top bar's entry for it."""

    id: PlatformId
    """The web's area id, also when the area is off."""
    name: str
    """Its own name, as its UI says it."""
    url: str
    """Its own UI, for people's browsers; empty when Wingman knows none (no link)."""
    area: bool
    """Whether Wingman's area for it is on: the top bar then opens the area, not ``url``."""


@dataclass(frozen=True, slots=True)
class Platforms:
    """The configured systems, in the top bar's order: segments-manager, then server-scan."""

    entries: tuple[Platform, ...] = ()

    def area(self, platform: PlatformId) -> bool:
        """Whether ``platform`` is configured and its area is on (else its routes answer 501)."""
        return any(entry.id == platform and entry.area for entry in self.entries)

    def links(self) -> tuple[Platform, ...]:
        """The entries the top bar can link: those whose UI Wingman knows."""
        return tuple(entry for entry in self.entries if entry.url)


def platforms(
    *,
    segments_url: str | None,
    server_scan_url: str | None,
    segments_area: bool,
    server_scan_area: bool,
) -> Platforms:
    """Each configured system (its UI's URL, ``None`` when it is not configured) and its area."""
    entries: list[Platform] = []
    if segments_url is not None:
        entries.append(Platform("segments", "Segments Manager", segments_url, segments_area))
    if server_scan_url is not None:
        entries.append(Platform("server-scan", "Server Scan", server_scan_url, server_scan_area))
    return Platforms(tuple(entries))
