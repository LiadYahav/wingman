"""``GET /api/day1/platforms`` and the two areas' switches (ADR-0047, ADR-0048; 2026-11-23).

The team keeps segments-manager and server-scan apart from Wingman: an
admin's top bar links to each one's own UI, and each area's routes answer 501
until ``DAY1_SEGMENTS_AREA`` or ``DAY1_SERVER_SCAN_AREA`` turns it on. The
cluster's network, the Nodes tab, placement and Inventory Management read the
same systems through other routes, which the switches leave on.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

import httpx
from fastapi import FastAPI

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import load_fleet
from wingman_day1.integrations.segments_manager.infrastructure.fake import (
    default_segments_file,
    load_fake_ledger,
)
from wingman_day1.integrations.server_scan.infrastructure.fakes.inventory import (
    FakeServerInventory,
    default_fleet_file,
)

Auth = Callable[[User], dict[str, str]]
PLATFORMS = "/api/day1/platforms"
URLS: Mapping[str, object] = {
    "segments_manager_url": "http://segments-manager-api.example:8000",
    "segments_manager_ui_url": "https://segments-manager.example",
    "server_scan_url": "http://server-scan-api.example:8000",
    "server_scan_ui_url": "https://server-scan.example",
}
AREA_PREFIXES = {
    "/api/day1/segments": "DAY1_SEGMENTS_AREA",
    "/api/day1/server-scan": "DAY1_SERVER_SCAN_AREA",
}
AMIT = "ocp4-prep-amit-site2-a"


def app_of(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    settings: Mapping[str, object] = URLS,
    *,
    systems: bool = True,
) -> FastAPI:
    """day1 on ``settings``, with segments-manager's and server-scan's fakes unless ``systems``."""
    rows = load_fleet(default_fleet_file())[0]
    return support.build_app(
        gitlab=gitlab,
        hub=None,
        identity=None,
        day2=FakeDay2Addons(),
        clock=clock,
        ledger=load_fake_ledger(default_segments_file()) if systems else None,
        inventory=FakeServerInventory(rows) if systems else None,
        **settings,
    )


async def get(app: FastAPI, path: str, headers: dict[str, str]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        return await client.get(path, headers=headers)


async def test_only_admins_read_the_platforms(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    app = app_of(support, gitlab, clock)
    assert (await get(app, PLATFORMS, {})).status_code == 401
    viewer = await get(app, PLATFORMS, auth(support.VIEWER))
    assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")
    assert (await get(app, PLATFORMS, auth(support.ALICE))).status_code == 200


async def test_each_system_links_its_own_ui_and_its_area_is_off_by_default(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    response = await get(app_of(support, gitlab, clock), PLATFORMS, auth(support.ALICE))
    assert response.json() == {
        "platforms": [
            {
                "id": "segments",
                "name": "Segments Manager",
                "url": "https://segments-manager.example",
                "area": False,
            },
            {
                "id": "server-scan",
                "name": "Server Scan",
                "url": "https://server-scan.example",
                "area": False,
            },
        ]
    }


async def test_without_a_ui_url_the_link_is_the_api_s_and_an_area_on_says_so(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    api_only = {
        "segments_manager_url": URLS["segments_manager_url"],
        "server_scan_url": URLS["server_scan_url"],
        "day1_server_scan_area": True,
    }
    app = app_of(support, gitlab, clock, api_only)
    body = (await get(app, PLATFORMS, auth(support.ALICE))).json()
    assert [(p["id"], p["url"], p["area"]) for p in body["platforms"]] == [
        ("segments", URLS["segments_manager_url"], False),
        ("server-scan", URLS["server_scan_url"], True),
    ]


async def test_a_system_day1_does_not_have_is_not_listed(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    app = app_of(support, gitlab, clock, {}, systems=False)
    assert (await get(app, PLATFORMS, auth(support.ALICE))).json() == {"platforms": []}


async def test_with_its_area_off_every_route_of_an_area_is_501_naming_the_switch(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    app = app_of(support, gitlab, clock)
    routes = [
        (method.upper(), path, setting)
        for path, operations in app.openapi()["paths"].items()
        for prefix, setting in AREA_PREFIXES.items()
        if path == prefix or path.startswith(f"{prefix}/")
        for method in operations
    ]
    assert {setting for _, _, setting in routes} == set(AREA_PREFIXES.values())
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://day1.test") as client:
        for method, path, setting in routes:
            url = re.sub(r"\{[^}]+\}", "x", path)
            response = await client.request(method, url, headers=auth(support.ALICE))
            body = response.json()
            assert (response.status_code, body["code"]) == (501, "FEATURE_DISABLED"), url
            assert body["details"] == {"setting": setting}, url


async def test_the_areas_off_leave_the_network_and_inventory_reads_on(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    app = app_of(support, gitlab, clock)
    network = await get(app, f"/api/day1/clusters/{AMIT}/network", auth(support.VIEWER))
    assert (network.status_code, network.json()["epg"]) == (200, "EPG_site2_HC_2490")
    assert (await get(app, "/api/day1/inventory", auth(support.VIEWER))).status_code == 200
