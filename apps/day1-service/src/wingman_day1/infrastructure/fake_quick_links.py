"""Quick Links with the fake fleet: the demo links file (ADR-0052).

``DAY1_FAKE_FLEET=true`` (development only) shows
``dev/fleet-fixtures/quick-links-links.yaml`` when ``QUICK_LINKS_FILE`` does
not exist, so the page demos without a chart.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

DEMO_LINKS_FILE: Final = Path("dev/fleet-fixtures/quick-links-links.yaml")


def default_demo_links_file() -> Path:
    """``dev/fleet-fixtures/quick-links-links.yaml`` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / DEMO_LINKS_FILE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{DEMO_LINKS_FILE} not found above this file")
