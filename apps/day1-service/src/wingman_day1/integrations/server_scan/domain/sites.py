"""server-scan's sites and fleet, as it counts them (ADR-0048).

The Server Scan area's Sites page shows server-scan's own counts: per
configured site and for the whole fleet, how many servers, per vendor, per
overall health and in maintenance, and the same per installation type and
per OpenShift state. These mirror server-scan's models
(``backend/app/api/v1/sites_schemas.py``) so the web can reuse its code.

Every map keeps server-scan's keys in its order, including a vendor, severity,
type or state it adds later: day1 never drops one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class VendorCount:
    """How many servers of one vendor a breakdown counts."""

    vendor: str
    count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Breakdown:
    """The counts of one slice of the fleet: a site, the fleet, or a type or state within one."""

    total: int
    by_vendor: tuple[VendorCount, ...]
    """In server-scan's vendor order, zeroes included."""
    by_health: Mapping[str, int]
    """Overall health severity to count, every severity present."""
    in_maintenance: int


@dataclass(frozen=True, slots=True, kw_only=True)
class FleetSummary(Breakdown):
    """A breakdown sliced further: per installation type and per OpenShift state."""

    by_installation_type: Mapping[str, Breakdown]
    """``HOSTED_CLUSTER``, ``MCE``, ``UPI``, ``UNCLASSIFIED``: what the server was named to be."""
    by_openshift_state: Mapping[str, Breakdown]
    """``AVAILABLE``, ``INSTALLED``, ``INSTALLED_TO_INVENTORY``: whether a cluster holds it."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SiteStats(FleetSummary):
    """One site's counts; ``unassigned`` counts the servers whose name carries no site."""

    site_id: str
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FleetSites:
    """``GET /api/v1/sites``: every configured site in server-scan's order, then the fleet."""

    sites: tuple[SiteStats, ...]
    fleet: FleetSummary
