"""The Server Scan area's response bodies (docs/notes/2026-11-13-server-scan-area-api.md).

In server-scan's own shapes (its ``backend/app/api/v1/sites_schemas.py``), so
server-scan's TypeScript types and pure functions apply as they are
(ADR-0048, decision 18 of the single-pane plan).
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel

from wingman_day1.domain.server_scan_sites import Breakdown, FleetSites, FleetSummary, SiteStats


class VendorCountOut(BaseModel):
    """How many servers of one vendor a breakdown counts."""

    vendor: str
    count: int


class BreakdownOut(BaseModel):
    """The counts of one slice of the fleet: a site, the fleet, or a type or state within one."""

    total: int
    by_vendor: list[VendorCountOut]
    by_health: dict[str, int]
    in_maintenance: int

    @classmethod
    def of_counts(cls, counts: Breakdown) -> BreakdownOut:
        """From the domain."""
        return cls(
            total=counts.total,
            by_vendor=_vendors(counts),
            by_health=dict(counts.by_health),
            in_maintenance=counts.in_maintenance,
        )


class FleetSummaryOut(BreakdownOut):
    """A breakdown sliced per installation type and per OpenShift state."""

    by_installation_type: dict[str, BreakdownOut]
    by_openshift_state: dict[str, BreakdownOut]

    @classmethod
    def of_summary(cls, summary: FleetSummary) -> FleetSummaryOut:
        """From the domain."""
        return cls(
            total=summary.total,
            by_vendor=_vendors(summary),
            by_health=dict(summary.by_health),
            in_maintenance=summary.in_maintenance,
            by_installation_type=_each(summary.by_installation_type),
            by_openshift_state=_each(summary.by_openshift_state),
        )


class SiteStatsOut(BaseModel):
    """One configured site (or ``unassigned``) and its counts: a sliced breakdown, named."""

    site_id: str
    name: str
    total: int
    by_vendor: list[VendorCountOut]
    by_health: dict[str, int]
    in_maintenance: int
    by_installation_type: dict[str, BreakdownOut]
    by_openshift_state: dict[str, BreakdownOut]

    @classmethod
    def of_site(cls, site: SiteStats) -> SiteStatsOut:
        """From the domain."""
        return cls(
            site_id=site.site_id,
            name=site.name,
            total=site.total,
            by_vendor=_vendors(site),
            by_health=dict(site.by_health),
            in_maintenance=site.in_maintenance,
            by_installation_type=_each(site.by_installation_type),
            by_openshift_state=_each(site.by_openshift_state),
        )


class SitesOut(BaseModel):
    """``GET /api/day1/server-scan/sites``: server-scan's ``GET /api/v1/sites``, typed."""

    items: list[SiteStatsOut]
    fleet: FleetSummaryOut

    @classmethod
    def of(cls, sites: FleetSites) -> SitesOut:
        """From the domain, in server-scan's order."""
        return cls(
            items=[SiteStatsOut.of_site(site) for site in sites.sites],
            fleet=FleetSummaryOut.of_summary(sites.fleet),
        )


def _vendors(counts: Breakdown) -> list[VendorCountOut]:
    return [VendorCountOut(vendor=v.vendor, count=v.count) for v in counts.by_vendor]


def _each(slices: Mapping[str, Breakdown]) -> dict[str, BreakdownOut]:
    return {name: BreakdownOut.of_counts(counts) for name, counts in slices.items()}
