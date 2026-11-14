"""server-scan's architecture diagrams, read from its UI (ADR-0048's 3.28.0 amendment).

server-scan's UI serves each diagram as a static page,
``GET <ui>/architecture/<slug>.html``; its API does not have them. So day1
reads them from server-scan's UI address (``SERVER_SCAN_UI_URL``, else
``SERVER_SCAN_URL``) with a client of its own that sends no token: the files
need none, and a token is not sent where it is not needed. The page is taken
only if it says it is a diagram (``is_diagram``): server-scan's nginx answers
an unknown path with its app and a 200.
"""

from __future__ import annotations

from typing import Final

import httpx

from wingman_day1.domain.errors import ServerScanDiagramNotFoundError, ServerScanUnavailableError
from wingman_day1.domain.server_scan_architecture import (
    DIAGRAM_MAX_BYTES,
    ArchitectureDiagram,
    is_diagram,
)
from wingman_day1.infrastructure.http import tls_verify
from wingman_day1.infrastructure.server_scan_record import fetch

DIAGRAM_PATH: Final = "/architecture/{slug}.html"
_ADDRESS: Final = "SERVER_SCAN_UI_URL must be server-scan's UI, which serves its diagrams"


def ui_client(
    *,
    base_url: str,
    verify: bool | str,
    timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None,
) -> httpx.AsyncClient:
    """A client at server-scan's UI that asks for HTML and sends no Authorization header."""
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=httpx.Timeout(timeout_seconds),
        verify=tls_verify(verify),
        transport=transport,
        headers={"Accept": "text/html"},
    )


async def read_diagram(client: httpx.AsyncClient, slug: str) -> ArchitectureDiagram:
    """The diagram ``slug`` (already checked against ``DIAGRAM_SLUG``), as server-scan serves it."""
    what = f"reading the diagram {slug}"
    response = await fetch(client, DIAGRAM_PATH.format(slug=slug), what=what)
    missing = f"server-scan's UI serves no diagram {slug!r} ({_ADDRESS})"
    if response.status_code == 404:
        raise ServerScanDiagramNotFoundError(missing)
    if response.status_code != 200:
        raise ServerScanUnavailableError(f"server-scan's UI answered {response.status_code} {what}")
    if len(response.content) > DIAGRAM_MAX_BYTES:
        raise ServerScanUnavailableError(
            f"server-scan's UI sent {len(response.content)} bytes {what}, more than a diagram"
        )
    html = response.text
    if not is_diagram(html):
        raise ServerScanDiagramNotFoundError(missing)
    return ArchitectureDiagram(slug=slug, html=html)
