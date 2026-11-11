"""HttpSegmentLedger: one segment from segments-manager, over httpx (ADR-0039).

Read only, and one call: ``GET /api/segments/by-segment?segment=<cidr>``,
which segments-manager serves without a token. A 404 is its "Segment not
found" (also its answer for a CIDR that is not a /24): ``None``. Any other
failure is ``SegmentsManagerUnavailableError``, so the EPG is unknown, never
"none" (ADR-0004). Nothing here writes to segments-manager.

``segment_record`` is also how the fake ledger reads its fixture, so the
fixture has segments-manager's own shape.
"""

from __future__ import annotations

import ssl
import time
from collections.abc import Mapping
from typing import Any, Final

import httpx

from wingman_core.observability.metrics import Dependency, WingmanMetrics
from wingman_day1.domain.errors import SegmentsManagerUnavailableError
from wingman_day1.domain.network import SegmentRecord
from wingman_day1.infrastructure.observed import Observer, SegmentsManagerOperation, Timer

JSON = Any
"""A decoded JSON value; narrowed where it is read."""

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
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            verify=verify
            if isinstance(verify, bool)
            else ssl.create_default_context(cafile=verify),
            transport=transport,
            headers={"Accept": "application/json"},
        )

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def segment(self, cidr: str) -> SegmentRecord | None:
        """See SegmentLedger.segment."""
        return await self._observer.call(SegmentsManagerOperation.GET_SEGMENT, self._read(cidr))

    async def _read(self, cidr: str) -> SegmentRecord | None:
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
                f"segments-manager returned a malformed segment {what}"
            ) from exc
        if record.segment != cidr:
            raise SegmentsManagerUnavailableError(
                f"segments-manager answered segment {record.segment} {what}"
            )
        return record


def segment_record(raw: JSON) -> SegmentRecord:
    """One segment as ``by-segment`` answers it; a malformed one raises Type/Key/ValueError.

    Unknown keys are ignored (live records still carry legacy ones).
    """
    if not isinstance(raw, dict):
        raise TypeError("a segment is not an object")
    return SegmentRecord(
        segment=_text(raw, "segment"),
        vlan_id=_vlan(raw),
        epg_name=_optional_text(raw, "epg_name"),
        cluster_name=_holder(raw),
        status=_optional_text(raw, "status"),
        type=_optional_text(raw, "type"),
        site=_optional_text(raw, "site"),
    )


def _text(raw: Mapping[str, JSON], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} is not a non-empty string")
    return value


def _optional_text(raw: Mapping[str, JSON], key: str) -> str | None:
    value = raw.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} is not a string")
    return value


def _vlan(raw: Mapping[str, JSON]) -> int | None:
    value = raw.get("vlan_id")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("vlan_id is not a number")
    return value


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
