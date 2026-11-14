"""server-scan's architecture diagrams through HttpServerInventory, the cache and the fake.

server-scan's UI serves each diagram as a static page,
``frontend/public/architecture/<slug>.html`` (archify's output, at 92146d3),
and answers any unknown path with its app's ``index.html`` and a 200 (its
``frontend/nginx.conf``): ADR-0048's 3.28.0 amendment.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import ServerScanDiagramNotFoundError, ServerScanUnavailableError
from wingman_day1.domain.server_scan_architecture import (
    DIAGRAM_MAX_BYTES,
    ArchitectureDiagram,
    is_diagram,
)
from wingman_day1.infrastructure.cached_server_scan import CachedServerInventory
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.fake_server_scan_architecture import (
    FakeDiagrams,
    default_diagram_file,
    load_diagrams,
)
from wingman_day1.infrastructure.server_scan import HttpServerInventory

API = "http://server-scan-api.inventory.svc:8000"
UI = "https://server-scan.example.internal"
TOKEN = "server-scan-viewer-token-never-shown-0003"
# The head of one of server-scan's diagrams, as archify writes it.
DIAGRAM = """<!DOCTYPE html>
<html lang="en" data-theme="dark" data-preset="classic">
<head>
  <meta charset="UTF-8">
  <meta name="generator" content="archify 2.16.0-dev.0">
  <title>Cisco UCS Central collector run Diagram</title>
</head>
<body><svg></svg></body>
</html>
"""
# What server-scan's nginx answers for a path it has no file for: its app.
SPA = (
    "<!doctype html><html><head><title>Server Scan</title></head>"
    '<body><div id="root"></div></body></html>'
)

Handler = Callable[[httpx.Request], httpx.Response]


def make(
    handler: Handler, *, ui_url: str = UI, metrics: WingmanMetrics | None = None
) -> tuple[HttpServerInventory, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    inventory = HttpServerInventory(
        base_url=API,
        ui_url=ui_url,
        token=TOKEN,
        timeout_seconds=2.0,
        metrics=metrics,
        transport=httpx.MockTransport(record),
        timer=iter(range(1000)).__next__,
    )
    return inventory, requests


def html(status: int, body: str | bytes = DIAGRAM) -> Handler:
    return lambda _request: httpx.Response(
        status, content=body, headers={"content-type": "text/html"}
    )


# ── The real adapter ──────────────────────────────────────────────────────────


async def test_a_diagram_is_read_from_server_scans_ui_without_a_token() -> None:
    inventory, requests = make(html(200))
    diagram = await inventory.architecture_diagram("ucs-central")
    assert diagram == ArchitectureDiagram(slug="ucs-central", html=DIAGRAM)
    (request,) = requests
    assert str(request.url) == f"{UI}/architecture/ucs-central.html"
    assert request.headers["Accept"] == "text/html"
    # The files need no token, so it does not go where it is not needed
    assert "Authorization" not in request.headers


async def test_without_a_ui_address_the_diagrams_are_read_where_the_api_is() -> None:
    inventory, requests = make(html(200), ui_url="")
    await inventory.architecture_diagram("nodes-status")
    assert str(requests[0].url) == f"{API}/architecture/nodes-status.html"


async def test_a_diagram_server_scan_does_not_serve_is_not_found_and_names_the_setting() -> None:
    inventory, _ = make(html(404, "Not Found"))
    with pytest.raises(ServerScanDiagramNotFoundError, match="SERVER_SCAN_UI_URL"):
        await inventory.architecture_diagram("gone")


async def test_server_scans_app_answered_for_a_missing_file_is_not_a_diagram() -> None:
    inventory, _ = make(html(200, SPA))
    with pytest.raises(ServerScanDiagramNotFoundError, match="serves no diagram 'gone'"):
        await inventory.architecture_diagram("gone")


@pytest.mark.parametrize("status", [302, 401, 403, 500, 503])
async def test_any_other_answer_is_unavailable(status: int) -> None:
    inventory, _ = make(html(status, ""))
    with pytest.raises(ServerScanUnavailableError, match=f"answered {status}"):
        await inventory.architecture_diagram("ucs-central")


async def test_server_scans_ui_unreachable_is_unavailable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    inventory, _ = make(refuse)
    with pytest.raises(ServerScanUnavailableError, match="unreachable reading the diagram"):
        await inventory.architecture_diagram("ucs-central")


async def test_a_page_larger_than_any_diagram_is_refused() -> None:
    inventory, _ = make(html(200, DIAGRAM + " " * DIAGRAM_MAX_BYTES))
    with pytest.raises(ServerScanUnavailableError, match="more than a diagram"):
        await inventory.architecture_diagram("ucs-central")


async def test_each_read_is_counted_by_its_outcome() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    ok, _ = make(html(200), metrics=metrics)
    await ok.architecture_diagram("x")
    for handler in (html(404, ""), html(200, SPA), html(500, "")):
        failing, _ = make(handler, metrics=metrics)
        with pytest.raises((ServerScanDiagramNotFoundError, ServerScanUnavailableError)):
            await failing.architecture_diagram("x")

    def count(outcome: str) -> float | None:
        labels = {
            "dependency": "server_scan",
            "operation": "get_architecture_diagram",
            "outcome": outcome,
        }
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert (count("ok"), count("not_found"), count("unavailable")) == (1, 2, 1)


def test_only_a_page_archify_made_is_a_diagram() -> None:
    assert is_diagram(DIAGRAM)
    assert is_diagram(DIAGRAM.replace('name="generator"', "name='generator'"))
    assert not is_diagram(SPA)
    # Only the document's own head counts, not a diagram quoted further down
    assert not is_diagram(SPA + " " * 10_000 + DIAGRAM)


# ── The cache ─────────────────────────────────────────────────────────────────


class CountingFake(FakeServerInventory):
    def __init__(self, diagrams: FakeDiagrams) -> None:
        super().__init__(diagrams=diagrams)
        self.diagram_reads = 0

    async def architecture_diagram(self, slug: str) -> ArchitectureDiagram:
        self.diagram_reads += 1
        return await super().architecture_diagram(slug)


async def test_each_diagram_is_cached_for_its_own_ttl() -> None:
    clock = [0.0]
    inner = CountingFake(FakeDiagrams({"a": DIAGRAM, "b": DIAGRAM}))
    cache = TtlCache(clock=lambda: clock[0])
    cached = CachedServerInventory(inner, cache, ttl=30, diagram_ttl=300)
    await cached.architecture_diagram("a")
    await cached.architecture_diagram("a")
    await cached.architecture_diagram("b")
    assert inner.diagram_reads == 2
    clock[0] = 299.0
    await cached.architecture_diagram("a")
    assert inner.diagram_reads == 2
    clock[0] = 301.0
    await cached.architecture_diagram("a")
    assert inner.diagram_reads == 3


async def test_a_missing_diagram_is_not_cached() -> None:
    diagrams = FakeDiagrams()
    inner = CountingFake(diagrams)
    cached = CachedServerInventory(inner, TtlCache(), ttl=30, diagram_ttl=300)
    for _ in range(2):
        with pytest.raises(ServerScanDiagramNotFoundError):
            await cached.architecture_diagram("a")
    assert inner.diagram_reads == 2


# ── The fake ──────────────────────────────────────────────────────────────────


async def test_the_fake_serves_its_pages_and_refuses_any_other_name() -> None:
    fake = FakeServerInventory(diagrams=FakeDiagrams({"full": DIAGRAM}))
    assert (await fake.architecture_diagram("full")).html == DIAGRAM
    with pytest.raises(ServerScanDiagramNotFoundError):
        await fake.architecture_diagram("other")
    fake.unavailable = True
    with pytest.raises(ServerScanUnavailableError):
        await fake.architecture_diagram("full")


async def test_the_fake_fleet_serves_its_stand_in_for_any_name() -> None:
    fake = FakeServerInventory(diagrams=load_diagrams(default_diagram_file()))
    diagram = await fake.architecture_diagram("ucs-central")
    assert is_diagram(diagram.html)
    assert "<h1>ucs-central</h1>" in diagram.html
    assert "{{slug}}" not in diagram.html
