"""The Architecture page's response body (docs/notes/2026-11-13-server-scan-area-api.md §11).

One of server-scan's diagrams, the page as its UI serves it, which the web
shows in a sandboxed frame (ADR-0048's 3.28.0 amendment).
"""

from __future__ import annotations

from pydantic import BaseModel

from wingman_day1.domain.server_scan_architecture import ArchitectureDiagram


class DiagramOut(BaseModel):
    """``GET /api/day1/server-scan/architecture/{slug}``: the diagram's name and its page."""

    slug: str
    html: str

    @classmethod
    def of(cls, diagram: ArchitectureDiagram) -> DiagramOut:
        """The answer for ``diagram``."""
        return cls(slug=diagram.slug, html=diagram.html)
