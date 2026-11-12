"""HttpLinkProbe: Quick Links' status checks (ADR-0052)."""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.quick_links import LinkState
from wingman_day1.infrastructure.link_probe import HttpLinkProbe

URL = "https://argocd.example.internal"
NOW = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]


def probe(
    handler: Handler, *, metrics: WingmanMetrics | None = None, **kw: object
) -> HttpLinkProbe:
    ticks = iter(float(i) / 10 for i in range(1000))
    return HttpLinkProbe(
        transport=httpx.MockTransport(handler),
        metrics=metrics,
        clock=lambda: NOW,
        timer=lambda: next(ticks),
        **kw,  # ty: ignore[invalid-argument-type]
    )


def answering(status: int, seen: list[httpx.Request] | None = None) -> Handler:
    async def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, headers={"Location": "https://login.example.internal"})

    return handler


@pytest.mark.parametrize("status", [200, 204, 301, 302, 401, 403])
async def test_an_answer_that_means_something_serves_is_up(status: int) -> None:
    reading = await probe(answering(status)).check(URL)
    assert reading.state is LinkState.UP
    assert reading.reason == f"answered {status}"
    assert reading.http_status == status
    assert reading.latency_ms == 100
    assert reading.checked_at == NOW


@pytest.mark.parametrize("status", [400, 404, 500, 503])
async def test_an_error_answer_is_down(status: int) -> None:
    reading = await probe(answering(status)).check(URL)
    assert reading.state is LinkState.DOWN
    assert reading.reason == f"answered {status}"


async def test_it_asks_head_without_credentials_and_does_not_follow_redirects() -> None:
    seen: list[httpx.Request] = []
    await probe(answering(302, seen)).check(URL)
    assert [(r.method, str(r.url)) for r in seen] == [("HEAD", URL)]
    assert "authorization" not in seen[0].headers
    assert "cookie" not in seen[0].headers
    assert seen[0].headers["user-agent"] == "wingman-quick-links"


@pytest.mark.parametrize("refused", [405, 501])
async def test_a_server_that_refuses_head_is_asked_with_get(refused: int) -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        return httpx.Response(refused if request.method == "HEAD" else 200, content=b"x" * 10)

    reading = await probe(handler).check(URL)
    assert seen == ["HEAD", "GET"]
    assert reading.state is LinkState.UP
    assert reading.http_status == 200


async def test_no_answer_in_time_is_down() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200)

    reading = await probe(handler, timeout_seconds=0.05).check(URL)
    assert reading.state is LinkState.DOWN
    assert reading.reason == "no answer within 0.05 s"
    assert reading.http_status is None


async def test_httpx_timeouts_are_down_too() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    reading = await probe(handler, timeout_seconds=3).check(URL)
    assert (reading.state, reading.reason) == (LinkState.DOWN, "no answer within 3 s")


async def test_no_connection_is_down_with_the_reason() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    reading = await probe(handler).check(URL)
    assert (reading.state, reading.reason) == (LinkState.DOWN, "connection failed (ConnectError)")


async def test_an_untrusted_certificate_is_unknown() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        try:
            raise ssl.SSLCertVerificationError("certificate verify failed")
        except ssl.SSLError as exc:
            raise httpx.ConnectError("tls", request=request) from exc

    reading = await probe(handler).check(URL)
    assert (reading.state, reading.reason) == (LinkState.UNKNOWN, "TLS certificate not trusted")


async def test_another_tls_failure_is_unknown() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("tls", request=request) from ssl.SSLError("handshake")

    reading = await probe(handler).check(URL)
    assert (reading.state, reading.reason) == (LinkState.UNKNOWN, "TLS handshake failed")


async def test_a_url_it_cannot_ask_is_unknown() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.UnsupportedProtocol("gopher", request=request)

    reading = await probe(handler).check("gopher://old.example.internal")
    assert (reading.state, reading.reason) == (LinkState.UNKNOWN, "not a URL Wingman can check")


async def test_at_most_concurrency_checks_run_at_once() -> None:
    running = 0
    most = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal running, most
        running += 1
        most = max(most, running)
        await asyncio.sleep(0.01)
        running -= 1
        return httpx.Response(200)

    checker = probe(handler, concurrency=3)
    readings = await asyncio.gather(*(checker.check(f"{URL}/{i}") for i in range(10)))
    assert all(r.state is LinkState.UP for r in readings)
    assert most == 3


async def test_every_check_is_counted_with_a_bounded_outcome() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/timeout":
            raise httpx.ReadTimeout("slow", request=request)
        if path == "/tls":
            raise httpx.ConnectError("tls", request=request) from ssl.SSLCertVerificationError()
        return httpx.Response(int(path.strip("/")))

    checker = probe(handler, metrics=metrics)
    for path in ("200", "404", "400", "503", "timeout", "tls"):
        await checker.check(f"{URL}/{path}")

    def count(outcome: str) -> float | None:
        return metrics.registry.get_sample_value(
            "wingman_dependency_requests_total",
            {"dependency": "link_check", "operation": "check_link", "outcome": outcome},
        )

    assert count("ok") == 1
    assert count("not_found") == 1
    assert count("rejected") == 1
    assert count("unavailable") == 2
    assert count("error") == 1
    labels = {
        tuple(sorted(s.labels.items()))
        for family in metrics.registry.collect()
        for s in family.samples
        if s.labels.get("dependency") == "link_check"
    }
    assert all("example.internal" not in str(label) for label in labels)


async def test_a_ca_bundle_is_read_when_the_probe_is_built(tmp_path: object) -> None:
    with pytest.raises(FileNotFoundError):
        HttpLinkProbe(verify="/nonexistent/ca.pem")
    checker = HttpLinkProbe(verify=False)
    await checker.aclose()
