"""segments-manager's GET answers, typed (ADR-0039, ADR-0047).

segments-manager publishes no schema for its reads, so these parsers are
Wingman's contract with them. A malformed answer raises Type/Key/ValueError,
which the adapter reports as ``SegmentsManagerUnavailableError``. In a list
of segments, one record that cannot be read is set aside with a sentence
saying why, and the others are kept: one bad legacy record does not hide the
ledger. Unknown keys are ignored (live records still carry legacy ones).

The fake ledger reads its fixture with ``segment_record`` too, so the fixture
has segments-manager's own shape.
"""

from __future__ import annotations

from collections.abc import Mapping

from wingman_day1.domain.network import SegmentRecord
from wingman_day1.domain.segments import SegmentList, SiteStats, TypeCount
from wingman_day1.infrastructure.http import JSON, optional_text, required_text


def segment_record(raw: JSON) -> SegmentRecord:
    """One segment as ``by-segment`` and ``GET /api/segments`` answer it."""
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


def segment_list(raw: JSON) -> SegmentList:
    """``GET /api/segments``: a list of segments; a record that cannot be read is set aside."""
    if not isinstance(raw, list):
        raise TypeError("the segments are not a list")
    records: list[SegmentRecord] = []
    unreadable: list[str] = []
    for item in raw:
        try:
            records.append(segment_record(item))
        except (ValueError, KeyError, TypeError) as exc:
            unreadable.append(_why(item, exc))
    return SegmentList(tuple(records), tuple(unreadable))


def site_names(raw: JSON) -> tuple[str, ...]:
    """``GET /api/sites``: ``{"sites": [...]}``."""
    if not isinstance(raw, dict) or not isinstance(sites := raw.get("sites"), list):
        raise TypeError("the sites are not a {sites: [...]} object")
    if not all(isinstance(site, str) and site for site in sites):
        raise TypeError("a site is not a non-empty string")
    return tuple(sites)


def site_stats(raw: JSON) -> tuple[SiteStats, ...]:
    """``GET /api/stats``: one entry per site, with its allocated count per type."""
    if not isinstance(raw, list):
        raise TypeError("the statistics are not a list")
    return tuple(_one_site(entry) for entry in raw)


def _one_site(raw: JSON) -> SiteStats:
    if not isinstance(raw, dict):
        raise TypeError("a site's statistics are not an object")
    by_type = raw.get("by_type", [])
    if not isinstance(by_type, list):
        raise TypeError("by_type is not a list")
    return SiteStats(
        site=required_text(raw, "site"),
        total_segments=_count(raw, "total_segments"),
        allocated=_count(raw, "allocated"),
        by_type=tuple(_type_count(item) for item in by_type),
    )


def _type_count(raw: JSON) -> TypeCount:
    if not isinstance(raw, dict):
        raise TypeError("a type's count is not an object")
    return TypeCount(type=required_text(raw, "type"), allocated=_count(raw, "allocated"))


def _why(item: JSON, exc: Exception) -> str:
    """One sentence for a record that could not be read, naming its segment when it has one."""
    segment = item.get("segment") if isinstance(item, dict) else None
    what = f"segment {segment}" if isinstance(segment, str) and segment else "a segment"
    reason = str(exc) if not isinstance(exc, KeyError) else f"it has no {exc.args[0]}"
    return f"segments-manager sent {what} Wingman could not read: {reason}"


def _number(raw: Mapping[str, JSON], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} is not a number")
    return value


def _count(raw: Mapping[str, JSON], key: str) -> int:
    value = _number(raw, key)
    if value is None or value < 0:
        raise ValueError(f"{key} is not a count")
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
