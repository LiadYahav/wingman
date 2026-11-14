"""``GET /api/day1/server-scan/architecture/{slug}`` (the note's §11, ADR-0048's 3.28.0 amendment).

One of server-scan's diagrams, the page its UI serves: admins only, off (501)
without server-scan, 404 for one it does not serve, 502 when it fails, 422
for a name that is not a diagram's.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.fake_server_scan_architecture import FakeDiagrams
from wingman_day1.ports import ServerInventory

Auth = Callable[[User], dict[str, str]]
PATH = "/api/day1/server-scan/architecture/"
PAGE = '<html><head><meta name="generator" content="archify 2.16.0"></head><body></body></html>'


async def call(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    headers: dict[str, str],
    slug: str = "runtime-architecture",
    *,
    inventory: ServerInventory | None = None,
) -> httpx.Response:
    """GET the diagram ``slug`` on an app over ``inventory`` (none: server-scan not configured)."""
    app = support.build_app(
        gitlab=gitlab,
        hub=None,
        identity=None,
        day2=FakeDay2Addons(),
        clock=clock,
        inventory=inventory,
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        return await client.get(PATH + slug, headers=headers)


def scan() -> FakeServerInventory:
    return FakeServerInventory(diagrams=FakeDiagrams({"runtime-architecture": PAGE}))


async def test_only_admins_read_a_diagram(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    anonymous = await call(support, gitlab, clock, {}, inventory=scan())
    assert anonymous.status_code == 401
    viewer = await call(support, gitlab, clock, auth(support.VIEWER), inventory=scan())
    assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")


async def test_the_diagram_is_the_page_server_scan_serves(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    response = await call(support, gitlab, clock, auth(support.ALICE), inventory=scan())
    assert response.status_code == 200, response.text
    assert response.json() == {"slug": "runtime-architecture", "html": PAGE}


async def test_without_server_scan_the_page_is_off(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    response = await call(support, gitlab, clock, auth(support.ALICE))
    assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
    assert "SERVER_SCAN_URL" in response.json()["detail"]


async def test_a_diagram_server_scan_does_not_serve_is_404(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    response = await call(support, gitlab, clock, auth(support.ALICE), "gone", inventory=scan())
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
    assert "gone" in response.json()["detail"]


async def test_server_scan_failing_is_502(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    down = scan()
    down.unavailable = True
    response = await call(support, gitlab, clock, auth(support.ALICE), inventory=down)
    assert (response.status_code, response.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")


@pytest.mark.parametrize("slug", ["Upper", "-dash", "dots.html", "a" * 65, "%2e%2e"])
async def test_a_name_no_diagram_has_is_refused_before_server_scan_is_asked(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth, slug: str
) -> None:
    response = await call(support, gitlab, clock, auth(support.ALICE), slug, inventory=scan())
    assert response.status_code == 422, response.text


async def test_a_name_with_a_slash_reaches_no_route(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    traversal = "%2e%2e%2fapi%2fv1%2fservers"
    response = await call(support, gitlab, clock, auth(support.ALICE), traversal, inventory=scan())
    assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
    assert "html" not in response.json()
