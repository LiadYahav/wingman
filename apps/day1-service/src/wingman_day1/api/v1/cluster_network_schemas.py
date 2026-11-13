"""The body of ``GET /clusters/{name}/network``: the file's segment and segments-manager's."""

from __future__ import annotations

from pydantic import BaseModel

from wingman_day1.domain.network import NetworkView, SegmentRecord


class SegmentLedgerOut(BaseModel):
    """What segments-manager records for the cluster's segment."""

    vlan_id: int | None
    cluster_name: str | list[str] | None
    """The cluster it is allocated to; a list for a shared ``UPI`` segment."""
    status: str | None
    type: str | None
    site: str | None

    @classmethod
    def of(cls, record: SegmentRecord) -> SegmentLedgerOut:
        """From segments-manager's record."""
        holder = record.cluster_name
        return cls(
            vlan_id=record.vlan_id,
            cluster_name=list(holder) if isinstance(holder, tuple) else holder,
            status=record.status,
            type=record.type,
            site=record.site,
        )


class ClusterNetworkOut(BaseModel):
    """``GET /clusters/{name}/network``: the file's network, the EPG, and what disagrees."""

    vlan_id: int | None
    """The file's ``vlanId``."""
    segment: str | None
    """The file's ``dhcp_values.network`` as its /24; ``None`` until it is allocated."""
    epg: str | None
    """segments-manager's ``epg_name`` for the segment."""
    ledger: SegmentLedgerOut | None
    """``None`` when segments-manager is off, failed (``ledger_error``) or has no such segment."""
    problems: list[str]
    """What segments-manager says that disagrees with the file, one sentence each."""
    ledger_error: str | None

    @classmethod
    def of(cls, view: NetworkView) -> ClusterNetworkOut:
        """From the network view."""
        return cls(
            vlan_id=view.vlan_id,
            segment=view.segment,
            epg=view.epg,
            ledger=SegmentLedgerOut.of(view.ledger) if view.ledger else None,
            problems=list(view.problems),
            ledger_error=view.ledger_error,
        )
