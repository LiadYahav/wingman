"""A cluster's network from its file, with the EPG from segments-manager (ADR-0039).

The VLAN and the segment are the file's (Git is the source of truth). When
segments-manager is configured and the file has a segment, it is asked for
that segment: its EPG is shown, and what it says that disagrees with the file
becomes a problem (``wingman_day1.domain.network``). segments-manager failing
never fails the read: the file's network is returned with ``ledger_error``.
Nothing here reads the MCE, and nothing writes to segments-manager.
"""

from __future__ import annotations

from wingman_day1.application.clusters import ClusterService
from wingman_day1.domain.errors import SegmentsManagerUnavailableError
from wingman_day1.domain.network import NetworkView, checked, file_network, unchecked
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.ports import SegmentLedger


class NetworkService:
    """``GET /clusters/{name}/network``."""

    def __init__(self, clusters: ClusterService, ledger: SegmentLedger | None) -> None:
        """``ledger`` is ``None`` when segments-manager is not configured: no EPG, no checks."""
        self._clusters = clusters
        self._ledger = ledger

    async def network(self, ref: ClusterRef) -> NetworkView:
        """The cluster's network; a missing file is ``NotFoundError``, as for the detail."""
        values = await self._clusters.values(ref)
        file = file_network(
            values.vlan_id if values else None, values.dhcp_network if values else None
        )
        if self._ledger is None or file.segment is None:
            return unchecked(file)
        try:
            record = await self._ledger.segment(file.segment)
        except SegmentsManagerUnavailableError as exc:
            return unchecked(
                file, ledger_error=f"{type(exc).__name__.removesuffix('Error')}: {exc}"
            )
        return checked(file, record, cluster=ref.name)
