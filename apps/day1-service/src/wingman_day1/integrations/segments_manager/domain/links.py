"""Links from a cluster to segments-manager, the platform's VLAN segment ledger.

The links need no call to segments-manager (the EPG day1 reads from it is
``wingman_day1.domain.network``, ADR-0039; docs/ecosystem/notes/segments-manager.md).
Its UI reads no URL parameters,
so no link opens one cluster's segment: the page opens the UI and names the
cluster to search for. Its API's open ``GET /api/segments/search?q=`` answers
the matching segments as JSON, which is the second link.

Both search by the cluster file's stem: it is the ``cluster_name`` the
allocate-segment workflow gives segments-manager (notes §4 and §5, ADR-0014),
not the chart's ``clusterName``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from urllib.parse import quote

SEARCH_PATH: Final = "/api/segments/search"


@dataclass(frozen=True, slots=True)
class SegmentsManagerLinks:
    """segments-manager's UI, and its API's search for one cluster's segment."""

    url: str
    search_url: str


def segments_manager_links(ui_url: str, cluster: str) -> SegmentsManagerLinks:
    """The links for the cluster file whose stem is ``cluster``; ``ui_url`` is the UI's base."""
    base = ui_url.rstrip("/")
    return SegmentsManagerLinks(
        url=f"{base}/",
        search_url=f"{base}{SEARCH_PATH}?q={quote(cluster, safe='')}",
    )
