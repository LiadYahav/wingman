"""HttpLinkProbe: is something answering at a URL? Quick Links' status dots (ADR-0052).

``HEAD <url>``, then ``GET <url>`` without reading its body when ``HEAD``
answers 405 or 501 (servers that do not serve it). Redirects are not
followed: a login redirect means something is serving. No credential is
ever sent. At most ``concurrency`` checks run at once, so a page of fifty
links never opens fifty connections; each has ``timeout_seconds`` overall.

Never raises: a failure is a ``down`` reading (no answer, no connection, an
error answer) or an ``unknown`` one (TLS could not be verified, so whether
the service is up is not known). Counted as ``dependency="link_check"``,
``operation="check_link"``; the URL is never a label (ADR-0010).
"""

from __future__ import annotations

import asyncio
import ssl
import time
from typing import Final

import httpx

from wingman_core.observability.metrics import Dependency, Outcome, WingmanMetrics
from wingman_core.ports.clock import Clock, system_clock
from wingman_day1.domain.quick_links import LinkReading, LinkState, state_of
from wingman_day1.infrastructure.observed import LinkCheckOperation, Timer

FALL_BACK_TO_GET: Final = frozenset({405, 501})
"""``HEAD`` answers after which the check asks again with ``GET``."""
USER_AGENT: Final = "wingman-quick-links"
NOT_FOUND: Final = 404
SERVER_ERROR: Final = 500


def tls_context(verify: bool | str) -> ssl.SSLContext | bool:
    """``True``/``False``, or a context trusting the CA bundle at ``verify`` (read now)."""
    if isinstance(verify, bool):
        return verify
    return ssl.create_default_context(cafile=verify)


def _tls_failure(exc: BaseException) -> str | None:
    """``TLS certificate not trusted`` (or another TLS reason) when ``exc`` came from TLS."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return "TLS certificate not trusted"
        if isinstance(current, ssl.SSLError):
            return "TLS handshake failed"
        current = current.__cause__ or current.__context__
    return None


def _outcome(reading: LinkReading) -> Outcome:
    """The metric's outcome for a reading.

    ``ok`` up, ``not_found`` 404, ``rejected`` another 4xx, ``unavailable``
    5xx or no answer, ``error`` unknown (TLS).
    """
    if reading.state is LinkState.UP:
        return Outcome.OK
    if reading.state is LinkState.UNKNOWN:
        return Outcome.ERROR
    if reading.http_status == NOT_FOUND:
        return Outcome.NOT_FOUND
    if reading.http_status is not None and reading.http_status < SERVER_ERROR:
        return Outcome.REJECTED
    return Outcome.UNAVAILABLE


class HttpLinkProbe:
    """A ``LinkProbe`` over httpx, one client for every URL."""

    def __init__(
        self,
        *,
        verify: bool | str = True,
        timeout_seconds: float = 3.0,
        concurrency: int = 8,
        metrics: WingmanMetrics | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock = system_clock,
        timer: Timer = time.perf_counter,
    ) -> None:
        """Check with ``verify`` (``True``/``False`` or a CA bundle path, read now).

        ``transport`` replaces the network in tests.
        """
        self._timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            verify=tls_context(verify),
            follow_redirects=False,
            transport=transport,
            headers={"User-Agent": USER_AGENT},
        )
        self._slots = asyncio.Semaphore(concurrency)
        self._metrics = metrics
        self._clock = clock
        self._timer = timer

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def check(self, url: str) -> LinkReading:
        """See LinkProbe.check."""
        async with self._slots:
            start = self._timer()
            reading = await self._check(url, start)
            if self._metrics is not None:
                self._metrics.observe_dependency(
                    Dependency.LINK_CHECK,
                    LinkCheckOperation.CHECK_LINK,
                    _outcome(reading),
                    self._timer() - start,
                )
            return reading

    async def _check(self, url: str, start: float) -> LinkReading:
        checked_at = self._clock()
        try:
            # One deadline for both requests: a HEAD that is refused leaves the GET the rest
            async with asyncio.timeout(self._timeout_seconds):
                status = (await self._client.head(url)).status_code
                if status in FALL_BACK_TO_GET:
                    async with self._client.stream("GET", url) as response:
                        status = response.status_code
        except (TimeoutError, httpx.TimeoutException):
            return LinkReading(
                url, LinkState.DOWN, f"no answer within {self._timeout_seconds:g} s", checked_at
            )
        except (httpx.UnsupportedProtocol, httpx.InvalidURL):
            return LinkReading(url, LinkState.UNKNOWN, "not a URL Wingman can check", checked_at)
        except httpx.TransportError as exc:
            if (tls := _tls_failure(exc)) is not None:
                return LinkReading(url, LinkState.UNKNOWN, tls, checked_at)
            return LinkReading(
                url, LinkState.DOWN, f"connection failed ({type(exc).__name__})", checked_at
            )
        return LinkReading(
            url,
            state_of(status),
            f"answered {status}",
            checked_at,
            http_status=status,
            latency_ms=round((self._timer() - start) * 1000),
        )
