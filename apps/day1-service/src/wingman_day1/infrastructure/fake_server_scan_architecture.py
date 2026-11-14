"""The fake server-scan's architecture diagrams (ADR-0048's 3.28.0 amendment).

Tests give each diagram's page; ``DAY1_FAKE_FLEET=true`` (development only)
serves one stand-in page for every name, from
``dev/fleet-fixtures/architecture-diagram.html`` with the name written in,
so the Architecture page shows something without server-scan. A name the
fake does not serve is ``ServerScanDiagramNotFoundError``, as the real one.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from wingman_day1.domain.errors import ServerScanDiagramNotFoundError
from wingman_day1.domain.server_scan_architecture import ArchitectureDiagram

DIAGRAM_FILE: Final = Path("dev") / "fleet-fixtures" / "architecture-diagram.html"


class FakeDiagrams:
    """server-scan's diagrams in memory: a page per name, else ``template`` for any name."""

    def __init__(self, pages: Mapping[str, str] | None = None, *, template: str = "") -> None:
        """Serve ``pages``; any other name gets ``template`` with ``{{slug}}`` written in."""
        self._pages = dict(pages or {})
        self._template = template

    def diagram(self, slug: str) -> ArchitectureDiagram:
        """The page for ``slug``; none is ``ServerScanDiagramNotFoundError``."""
        html = self._pages.get(slug)
        if html is None and self._template:
            html = self._template.replace("{{slug}}", slug)
        if html is None:
            missing = f"server-scan's UI serves no diagram {slug!r} (fake)"
            raise ServerScanDiagramNotFoundError(missing)
        return ArchitectureDiagram(slug=slug, html=html)


def default_diagram_file() -> Path:
    """``dev/fleet-fixtures/architecture-diagram.html`` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / DIAGRAM_FILE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{DIAGRAM_FILE} not found above {Path(__file__).resolve()}")


def load_diagrams(path: Path) -> FakeDiagrams:
    """The fake fleet's diagrams: the stand-in page at ``path`` for every name."""
    return FakeDiagrams(template=path.read_text(encoding="utf-8"))
