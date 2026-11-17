"""server-scan's architecture diagrams, as its UI serves them (ADR-0048's 3.28.0 amendment).

server-scan's Architecture page frames one pre-built diagram per collector
plus the full flow: self-contained HTML pages that archify generated from
its ADRs and provider code, served by its UI's nginx as static files
(``frontend/public/architecture/<slug>.html``). They are not on its API and
need no token. Wingman shows them as server-scan serves them, never a copy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

DIAGRAM_SLUG: Final = r"^[a-z0-9][a-z0-9-]{0,63}$"
"""A diagram's name, as server-scan names its files: lowercase, digits and dashes."""

DIAGRAM_MAX_BYTES: Final = 8 * 1024 * 1024
"""The largest page day1 takes; server-scan's are about 0.7 MB each."""

_GENERATOR: Final = re.compile(
    r"<meta\s+name=[\"']generator[\"']\s+content=[\"']archify", re.IGNORECASE
)
_HEAD: Final = 8192
"""How far into a page its ``generator`` is looked for: archify writes it in the first lines."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ArchitectureDiagram:
    """One of server-scan's diagrams: its name and its page, as server-scan serves it."""

    slug: str
    html: str


def is_diagram(html: str) -> bool:
    """Whether ``html`` is one of server-scan's diagrams, which say they were made by archify.

    server-scan's nginx answers any unknown path with its app's
    ``index.html`` and a 200, so a missing diagram does not look missing.
    """
    return _GENERATOR.search(html, 0, _HEAD) is not None
