"""Time as a dependency, so tests and the fake control it."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]
"""Returns the current time, timezone-aware."""


def system_clock() -> datetime:
    """The real clock, in UTC."""
    return datetime.now(UTC)
