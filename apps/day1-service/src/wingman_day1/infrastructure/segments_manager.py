"""HttpSegmentLedger: segments-manager's open reads, over httpx (ADR-0039, ADR-0047).

Read only, and only GETs segments-manager serves without a token:

- ``GET /api/segments/by-segment?segment=<cidr>``: one segment, for the
  cluster page's EPG. A 404 is its "Segment not found" (also its answer for a
  CIDR that is not a /24): ``None``.
- ``GET /api/sites``, ``GET /api/stats`` and ``GET /api/segments`` (with its
  ``site``, ``status`` and ``type`` filters, and ``fresh=true`` for its
  Refresh button), for the Segments area.

Any other answer, or a malformed one, is ``SegmentsManagerUnavailableError``,
so what segments-manager says is unknown, never "none" (ADR-0004). Nothing
here writes to segments-manager. The answers are typed in
``segments_manager_parse``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Final

import httpx

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.errors import SegmentsManagerUnavailableError
from wingman_day1.domain.network import SegmentRecord
from wingman_day1.domain.segments import ALL_SEGMENTS, SegmentList, SegmentQuery, SiteStats
from wingman_day1.infrastructure.http import JSON, json_client
from wingman_day1.infrastructure.observed import Observer, SegmentsManagerOperation, Timer
from wingman_day1.infrastructure.segments_manager_parse import (
    segment_list,
    segment_record,
    site_names,
    site_stats,
)

BY_SEGMENT_PATH: Final = "/api/segments/by-segment"
SITES_PATH: Final = "/api/sites"
STATS_PATH: Final = "/api/stats"
SEGMENTS_PATH: Final = "/api/segments"


class HttpSegmentLedger:
    """A ``SegmentLedger`` over segments-manager's REST API."""

    def __init__(
        self,
        *,
        base_url: str,
        verify: bool | str = True,
        timeout_seconds: float = 5.0,
        metrics: WingmanMetrics | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timer: Timer = time.perf_counter,
    ) -> None:
        """Read segments-manager at ``base_url``, its API (no token: its reads are open).

        ``verify`` is ``True``/``False`` or a CA bundle path (read now, so a
        missing bundle stops start-up); ``transport`` is for tests.
        """
        self._observer = Observer(Dependency.SEGMENTS_MANAGER, metrics, timer=timer)
        self._client = json_client(
            base_url=base_url,
            verify=verify,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def segment(self, cidr: str) -> SegmentRecord | None:
        """See SegmentLedger.segment."""
        return await self._observer.call(SegmentsManagerOperation.GET_SEGMENT, self._one(cidr))

    async def sites(self) -> tuple[str, ...]:
        """See SegmentLedger.sites."""
        read = self._read(SITES_PATH, {}, "reading the sites", site_names)
        return await self._observer.call(SegmentsManagerOperation.LIST_SITES, read)

    async def stats(self) -> tuple[SiteStats, ...]:
        """See SegmentLedger.stats."""
        read = self._read(STATS_PATH, {}, "reading the statistics", site_stats)
        return await self._observer.call(SegmentsManagerOperation.GET_STATS, read)

    async def segments(
        self, query: SegmentQuery = ALL_SEGMENTS, *, fresh: bool = False
    ) -> SegmentList:
        """See SegmentLedger.segments."""
        params = {
            key: value
            for key, value in (("site", query.site), ("status", query.status), ("type", query.type))
            if value is not None
        }
        if fresh:
            params["fresh"] = "true"
        operation = (
            SegmentsManagerOperation.REFRESH_SEGMENTS
            if fresh
            else SegmentsManagerOperation.LIST_SEGMENTS
        )
        read = self._read(SEGMENTS_PATH, params, "reading the segments", segment_list)
        return await self._observer.call(operation, read)

    async def _one(self, cidr: str) -> SegmentRecord | None:
        what = f"reading segment {cidr}"
        response = await self._get(BY_SEGMENT_PATH, {"segment": cidr}, what)
        if response.status_code == 404:
            return None
        record = _parsed(response, what, segment_record)
        if record.segment != cidr:
            raise SegmentsManagerUnavailableError(
                f"segments-manager answered segment {record.segment} {what}"
            )
        return record

    async def _read[T](
        self, path: str, params: dict[str, str], what: str, parse: Callable[[JSON], T]
    ) -> T:
        return _parsed(await self._get(path, params, what), what, parse)

    async def _get(self, path: str, params: dict[str, str], what: str) -> httpx.Response:
        """The answer to one GET: 200, or 404 for one segment; anything else is unavailable."""
        try:
            response = await self._client.get(path, params=params)
        except httpx.TransportError as exc:
            raise SegmentsManagerUnavailableError(
                f"segments-manager unreachable {what}: {type(exc).__name__}"
            ) from exc
        answers = (200, 404) if path == BY_SEGMENT_PATH else (200,)
        if response.status_code not in answers:
            raise SegmentsManagerUnavailableError(
                f"segments-manager answered {response.status_code} {what}"
            )
        return response


def _parsed[T](response: httpx.Response, what: str, parse: Callable[[JSON], T]) -> T:
    """``parse`` of the JSON body; a body it cannot read is unavailable, as malformed."""
    try:
        return parse(response.json())
    except (ValueError, KeyError, TypeError) as exc:
        raise SegmentsManagerUnavailableError(
            f"segments-manager returned a malformed answer {what}"
        ) from exc
