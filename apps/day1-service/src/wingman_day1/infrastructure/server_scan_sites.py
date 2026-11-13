"""server-scan's ``GET /api/v1/sites``, read into the domain (ADR-0048).

The shape is server-scan's ``SiteStatsListResponse``
(``backend/app/api/v1/sites_schemas.py`` in team-redbull/server-scan at
92146d3): ``{items: [SiteStats], fleet: FleetSummary}``, where every site, the
fleet and each slice is a breakdown (``total``, ``by_vendor``, ``by_health``,
``in_maintenance``). Read strictly: a count that is not a whole number, a map
that is not ``str`` to a count or a breakdown, a missing field, all raise
Type/Key/ValueError, which the adapter turns into "unavailable", never into
zeroes. Every key is kept, in server-scan's order.
"""

from __future__ import annotations

from collections.abc import Mapping

from wingman_day1.domain.server_scan_sites import (
    Breakdown,
    FleetSites,
    FleetSummary,
    SiteStats,
    VendorCount,
)
from wingman_day1.infrastructure.http import JSON, required_text


def fleet_sites(raw: JSON) -> FleetSites:
    """The whole answer; a malformed one raises Type/Key/ValueError."""
    body = _object(raw, "the answer")
    items = body["items"]
    if not isinstance(items, list):
        raise TypeError("items is not a list")
    return FleetSites(
        sites=tuple(_site(item) for item in items),
        fleet=_summary(_object(body["fleet"], "fleet")),
    )


def _site(raw: JSON) -> SiteStats:
    site = _object(raw, "a site")
    summary = _summary(site)
    return SiteStats(
        site_id=required_text(site, "site_id"),
        name=required_text(site, "name"),
        total=summary.total,
        by_vendor=summary.by_vendor,
        by_health=summary.by_health,
        in_maintenance=summary.in_maintenance,
        by_installation_type=summary.by_installation_type,
        by_openshift_state=summary.by_openshift_state,
    )


def _summary(raw: Mapping[str, JSON]) -> FleetSummary:
    counts = _breakdown(raw)
    return FleetSummary(
        total=counts.total,
        by_vendor=counts.by_vendor,
        by_health=counts.by_health,
        in_maintenance=counts.in_maintenance,
        by_installation_type=_slices(raw, "by_installation_type"),
        by_openshift_state=_slices(raw, "by_openshift_state"),
    )


def _breakdown(raw: Mapping[str, JSON]) -> Breakdown:
    vendors = raw["by_vendor"]
    if not isinstance(vendors, list):
        raise TypeError("by_vendor is not a list")
    health = _object(raw["by_health"], "by_health")
    return Breakdown(
        total=_count(raw, "total"),
        by_vendor=tuple(_vendor(entry) for entry in vendors),
        by_health={_key(key): _count(health, key) for key in health},
        in_maintenance=_count(raw, "in_maintenance"),
    )


def _slices(raw: Mapping[str, JSON], key: str) -> dict[str, Breakdown]:
    slices = _object(raw[key], key)
    return {
        _key(name): _breakdown(_object(value, f"{key}.{name}")) for name, value in slices.items()
    }


def _vendor(raw: JSON) -> VendorCount:
    entry = _object(raw, "a by_vendor entry")
    return VendorCount(vendor=required_text(entry, "vendor"), count=_count(entry, "count"))


def _object(raw: JSON, what: str) -> Mapping[str, JSON]:
    if not isinstance(raw, dict):
        raise TypeError(f"{what} is not an object")
    return raw


def _key(key: JSON) -> str:
    if not isinstance(key, str) or not key:
        raise ValueError("a key is not a non-empty string")
    return key


def _count(raw: Mapping[str, JSON], key: str) -> int:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} is not a count")
    return value
