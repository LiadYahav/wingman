"""FakeSegmentLedger: segments-manager in memory (ADR-0039).

Tests seed it directly; ``DAY1_FAKE_FLEET=true`` (development only) seeds it
from ``dev/fleet-fixtures/segments.yaml``, written in segments-manager's own
``by-segment`` shape and read by the HTTP adapter's parser. It raises the
same error as the real adapter.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Final

import yaml

from wingman_day1.domain.errors import SegmentsManagerUnavailableError
from wingman_day1.domain.network import SegmentRecord
from wingman_day1.infrastructure.segments_manager import segment_record

SEGMENTS_FILE: Final = Path("dev/fleet-fixtures/segments.yaml")


class FakeSegmentLedger:
    """A ``SegmentLedger`` over seeded records; ``unavailable`` fails every read, as if down."""

    def __init__(self, records: Iterable[SegmentRecord] = (), *, unavailable: bool = False) -> None:
        """Seed the ledger."""
        self._records = {record.segment: record for record in records}
        self.unavailable = unavailable
        self.reads = 0
        """How many times ``segment`` was called."""

    async def segment(self, cidr: str) -> SegmentRecord | None:
        """See SegmentLedger.segment."""
        self.reads += 1
        if self.unavailable:
            raise SegmentsManagerUnavailableError(
                f"segments-manager answered 503 reading segment {cidr}"
            )
        return self._records.get(cidr)


def default_segments_file() -> Path:
    """``dev/fleet-fixtures/segments.yaml`` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / SEGMENTS_FILE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{SEGMENTS_FILE} not found above this file")


def load_segments(path: Path) -> list[SegmentRecord]:
    """The segments (``items``, in segments-manager's ``by-segment`` shape) of a fixture."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise TypeError(f"{path}: expected a mapping with an 'items' list")
    records = [segment_record(item) for item in raw["items"]]
    segments = [record.segment for record in records]
    if len(set(segments)) != len(segments):
        raise ValueError(f"{path}: a segment is listed twice")
    return records
