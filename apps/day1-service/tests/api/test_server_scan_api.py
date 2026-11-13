"""``/api/day1/server-scan`` (docs/notes/2026-11-13-server-scan-area-api.md, ADR-0048).

Admins only (decision 13, until RBAC); off (501) without server-scan; 502 when
it fails or refuses Wingman's token. Built on the fake fleet of
``dev/fleet-fixtures/servers.yaml`` and its site catalog.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import ServerScanDeniedError
from wingman_day1.domain.server_scan_sites import FleetSites
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import (
    FakeServerInventory,
    default_fleet_file,
    load_fleet,
)
from wingman_day1.infrastructure.fake_server_scan_sites import load_site_catalog
from wingman_day1.ports import ServerInventory

Auth = Callable[[User], dict[str, str]]
SITES = "/api/day1/server-scan/sites"


async def call(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    headers: dict[str, str],
    *,
    inventory: ServerInventory | None = None,
) -> httpx.Response:
    """GET the sites on an app over ``inventory`` (none: server-scan not configured)."""
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
        return await client.get(SITES, headers=headers)


def fleet() -> FakeServerInventory:
    rows, _ = load_fleet(default_fleet_file())
    return FakeServerInventory(rows, sites=load_site_catalog(default_fleet_file()))


class DeniedInventory(FakeServerInventory):
    """server-scan refusing the viewer token."""

    async def sites(self) -> FleetSites:
        raise ServerScanDeniedError(
            "server-scan refused Wingman's token (401): check SERVER_SCAN_TOKEN"
        )


async def test_only_admins_read_the_sites(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    anonymous = await call(support, gitlab, clock, {}, inventory=fleet())
    assert anonymous.status_code == 401
    viewer = await call(support, gitlab, clock, auth(support.VIEWER), inventory=fleet())
    assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")
    admin = await call(support, gitlab, clock, auth(support.ALICE), inventory=fleet())
    assert admin.status_code == 200


async def test_without_server_scan_the_area_is_off(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    response = await call(support, gitlab, clock, auth(support.ALICE))
    assert response.status_code == 501
    body = response.json()
    assert body["code"] == "FEATURE_DISABLED"
    assert "SERVER_SCAN_URL" in body["detail"]


async def test_server_scan_failing_or_refusing_the_token_is_502(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    down = FakeServerInventory(unavailable=True)
    response = await call(support, gitlab, clock, auth(support.ALICE), inventory=down)
    assert (response.status_code, response.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    refused = await call(support, gitlab, clock, auth(support.ALICE), inventory=DeniedInventory())
    assert (refused.status_code, refused.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    assert "SERVER_SCAN_TOKEN" in refused.json()["detail"]


async def test_the_sites_in_server_scan_s_shape(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    rows, _ = load_fleet(default_fleet_file())
    response = await call(support, gitlab, clock, auth(support.ALICE), inventory=fleet())
    assert response.status_code == 200, response.text
    body = response.json()
    assert list(body) == ["items", "fleet"]
    items = body["items"]
    assert [(s["site_id"], s["name"]) for s in items] == [
        ("site1", "Site 1"),
        ("site2", "Site 2"),
        ("site3", "Site 3"),
        ("unassigned", "Unassigned"),
    ]
    assert list(items[0]) == [
        "site_id",
        "name",
        "total",
        "by_vendor",
        "by_health",
        "in_maintenance",
        "by_installation_type",
        "by_openshift_state",
    ]
    site3 = items[2]
    assert site3["total"] == 0
    assert site3["by_health"] == {
        "UNKNOWN": 0,
        "HEALTHY": 0,
        "WARNING": 0,
        "MAJOR": 0,
        "CRITICAL": 0,
    }
    assert [v["vendor"] for v in site3["by_vendor"]] == [
        "dell",
        "cisco",
        "hp",
        "standalone",
        "kubevirt",
    ]

    fleet_ = body["fleet"]
    assert fleet_["total"] == len(rows) == sum(s["total"] for s in items)
    for key in ("by_installation_type", "by_openshift_state"):
        assert sum(b["total"] for b in fleet_[key].values()) == fleet_["total"], key
    assert sum(fleet_["by_health"].values()) == fleet_["total"]
    assert fleet_["in_maintenance"] == sum(r.maintenance for r in rows)
    assert list(fleet_["by_openshift_state"]) == [
        "AVAILABLE",
        "INSTALLED",
        "INSTALLED_TO_INVENTORY",
    ]
    assert fleet_["by_installation_type"]["HOSTED_CLUSTER"]["total"] == len(rows)
