"""segments-manager's answer for one segment, typed (ADR-0039).

segments-manager publishes no schema for its reads, so this parser is
Wingman's contract with it. A malformed answer raises Type/Key/ValueError,
which the adapter reports as ``SegmentsManagerUnavailableError``. Unknown
keys are ignored (live records still carry legacy ones).

The fake ledger reads its fixture with ``segment_record`` too, so the fixture
has segments-manager's own shape.

What it follows upstream, and at which version: docs/integrations/segments-manager.yaml.
"""

from __future__ import annotations

from collections.abc import Mapping

from wingman_day1.domain.network import SegmentRecord
from wingman_day1.infrastructure.http import JSON, optional_text, required_text


def segment_record(raw: JSON) -> SegmentRecord:
    """One segment as ``by-segment`` answers it."""
    if not isinstance(raw, dict):
        raise TypeError("a segment is not an object")
    return SegmentRecord(
        segment=required_text(raw, "segment"),
        vlan_id=_number(raw, "vlan_id"),
        epg_name=optional_text(raw, "epg_name"),
        cluster_name=_holder(raw),
        status=optional_text(raw, "status"),
        type=optional_text(raw, "type"),
        site=optional_text(raw, "site"),
        dhcp=_flag(raw, "dhcp"),
        allocated_at=optional_text(raw, "allocated_at"),
    )


def _number(raw: Mapping[str, JSON], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} is not a number")
    return value


def _flag(raw: Mapping[str, JSON], key: str) -> bool | None:
    value = raw.get(key)
    if value is None or isinstance(value, bool):
        return value
    raise TypeError(f"{key} is not true or false")


def _holder(raw: Mapping[str, JSON]) -> str | tuple[str, ...] | None:
    """``cluster_name``: one stem, or a list of them for a shared UPI segment."""
    value = raw.get("cluster_name")
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(name, str) for name in value):
        return tuple(value)
    raise TypeError("cluster_name is not a string or a list of strings")
