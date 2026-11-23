"""HttpSegmentLedger: segments-manager's open read of one segment, over httpx (ADR-0039).

Read only, one GET segments-manager serves without a token:
``GET /api/segments/by-segment?segment=<cidr>``, for the cluster page's EPG.
A 404 is its "Segment not found" (also its answer for a CIDR that is not a
/24): ``None``.

Any other answer, or a malformed one, is ``SegmentsManagerUnavailableError``,
so what segments-manager says is unknown, never "none" (ADR-0004). Nothing
here writes to segments-manager. The answer is typed in ``parse``.

What it follows upstream, and at which version: docs/integrations/segments-manager.yaml.
"""

from __future__ import annotations

import time
from typing import Final

import httpx

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.errors import SegmentsManagerUnavailableError
from wingman_day1.domain.network import SegmentRecord
from wingman_day1.infrastructure.http import json_client
from wingman_day1.infrastructure.observed import Observer, SegmentsManagerOperation, Timer
from wingman_day1.integrations.segments_manager.infrastructure.parse import segment_record

BY_SEGMENT_PATH: Final = "/api/segments/by-segment"


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

    async def _one(self, cidr: str) -> SegmentRecord | None:
        what = f"reading segment {cidr}"
        try:
            response = await self._client.get(BY_SEGMENT_PATH, params={"segment": cidr})
        except httpx.TransportError as exc:
            raise SegmentsManagerUnavailableError(
                f"segments-manager unreachable {what}: {type(exc).__name__}"
            ) from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise SegmentsManagerUnavailableError(
                f"segments-manager answered {response.status_code} {what}"
            )
        try:
            record = segment_record(response.json())
        except (ValueError, KeyError, TypeError) as exc:
            raise SegmentsManagerUnavailableError(
                f"segments-manager returned a malformed answer {what}"
            ) from exc
        if record.segment != cidr:
            raise SegmentsManagerUnavailableError(
                f"segments-manager answered segment {record.segment} {what}"
            )
        return record
