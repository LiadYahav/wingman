"""The Segments area's response bodies (docs/notes/2026-11-13-segments-area-api.md, ADR-0047).

Apart from ``schemas.py`` so the area's shapes read as one contract.
segments-manager's values pass through unchanged; Wingman adds the holders.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.segments import Holder, Mismatch, SegmentRow, SegmentsView, SiteStats


class SitesOut(BaseModel):
    """``GET /api/day1/segments/sites``: segments-manager's sites, in its order."""

    sites: list[str]

    @classmethod
    def of(cls, sites: Sequence[str]) -> SitesOut:
        """From the ledger."""
        return cls(sites=list(sites))


class TypeCountOut(BaseModel):
    """A site's segments allocated as one type: a count, never "x of y"."""

    type: str
    allocated: int


class SiteStatsOut(BaseModel):
    """One site's card."""

    site: str
    total_segments: int
    allocated: int
    by_type: list[TypeCountOut]


class StatsOut(BaseModel):
    """``GET /api/day1/segments/stats``: one entry per site, in segments-manager's order."""

    sites: list[SiteStatsOut]

    @classmethod
    def of(cls, stats: Sequence[SiteStats]) -> StatsOut:
        """From the ledger."""
        return cls(
            sites=[
                SiteStatsOut(
                    site=s.site,
                    total_segments=s.total_segments,
                    allocated=s.allocated,
                    by_type=[TypeCountOut(type=t.type, allocated=t.allocated) for t in s.by_type],
                )
                for s in stats
            ]
        )


class Day1PlaceOut(BaseModel):
    """Where a holder's cluster file is in the day1 repo: its page's ``site`` and ``mce``."""

    site: str
    mce: str

    @classmethod
    def of(cls, ref: ClusterRef | None) -> Day1PlaceOut | None:
        """From the file's place; ``None`` for a holder without one."""
        return cls(site=ref.site, mce=ref.mce) if ref is not None else None


class HolderOut(BaseModel):
    """One name the segment is allocated to."""

    name: str
    day1: Day1PlaceOut | None
    """``None`` for an MCE, a UPI cluster, a name day1 does not have, or one two files share."""

    @classmethod
    def of(cls, holder: Holder) -> HolderOut:
        """From the domain."""
        return cls(name=holder.name, day1=Day1PlaceOut.of(holder.ref))


class MismatchOut(BaseModel):
    """Where segments-manager disagrees with a cluster file: the file, and the sentence."""

    cluster: str
    site: str
    mce: str
    detail: str

    @classmethod
    def of(cls, mismatch: Mismatch) -> MismatchOut:
        """From the domain."""
        ref = mismatch.cluster
        return cls(cluster=ref.name, site=ref.site, mce=ref.mce, detail=mismatch.detail)


class SegmentOut(BaseModel):
    """One segment: segments-manager's record, unchanged, and its holders."""

    segment: str
    site: str | None
    vlan_id: int | None
    epg_name: str | None
    dhcp: bool | None
    status: str | None
    type: str | None
    cluster_name: str | list[str] | None
    """One name; a list for a shared ``UPI`` segment; ``None`` while Available."""
    allocated_at: str | None
    holders: list[HolderOut]
    mismatches: list[MismatchOut]
    """ADR-0039's checks from the segment's side; empty when they agree or Git says nothing."""

    @classmethod
    def of(cls, row: SegmentRow) -> SegmentOut:
        """From the domain."""
        record = row.record
        holder = record.cluster_name
        return cls(
            segment=record.segment,
            site=record.site,
            vlan_id=record.vlan_id,
            epg_name=record.epg_name,
            dhcp=record.dhcp,
            status=record.status,
            type=record.type,
            cluster_name=list(holder) if isinstance(holder, tuple) else holder,
            allocated_at=record.allocated_at,
            holders=[HolderOut.of(h) for h in row.holders],
            mismatches=[MismatchOut.of(m) for m in row.mismatches],
        )


class SegmentsOut(BaseModel):
    """``GET /api/day1/segments``."""

    segments: list[SegmentOut]
    unreadable: list[str]
    """Records segments-manager sent that Wingman could not read, one sentence each."""
    clusters_error: str | None
    """Why the day1 repo's cluster files could not be read: every holder is then unlinked."""
    fresh: bool
    """``True`` when segments-manager's database was read just now."""

    @classmethod
    def of(cls, view: SegmentsView) -> SegmentsOut:
        """From the domain."""
        return cls(
            segments=[SegmentOut.of(row) for row in view.rows],
            unreadable=list(view.unreadable),
            clusters_error=view.clusters_error,
            fresh=view.fresh,
        )
