"""``GET /api/day1/server-scan/confs`` (docs/notes/2026-11-13-server-scan-area-api.md §10).

The Server Scan area's Confs page (ADR-0048's 3.29.0 amendment): server-scan's
hardware catalog in its shape. Admins only; off (501) without server-scan; 502
when it fails or refuses Wingman's token. Built on the fake fleet's catalog,
``dev/fleet-fixtures/confs.yaml``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import ServerScanDeniedError
from wingman_day1.domain.server_scan_confs import ConfList
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.fake_server_scan_confs import default_confs_file, load_confs
from wingman_day1.ports import ServerInventory

Auth = Callable[[User], dict[str, str]]
CONFS = "/api/day1/server-scan/confs"


async def call(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    headers: dict[str, str],
    *,
    inventory: ServerInventory | None = None,
) -> httpx.Response:
    """GET the confs on an app over ``inventory`` (none: server-scan not configured)."""
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
        return await client.get(CONFS, headers=headers)


def catalog() -> FakeServerInventory:
    return FakeServerInventory(confs=load_confs(default_confs_file()))


class DeniedInventory(FakeServerInventory):
    """server-scan refusing the viewer token."""

    async def confs(self) -> ConfList:
        raise ServerScanDeniedError(
            "server-scan refused Wingman's token (401) listing confs: check SERVER_SCAN_TOKEN"
        )


async def test_only_admins_read_the_confs(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    anonymous = await call(support, gitlab, clock, {}, inventory=catalog())
    assert anonymous.status_code == 401
    viewer = await call(support, gitlab, clock, auth(support.VIEWER), inventory=catalog())
    assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")
    admin = await call(support, gitlab, clock, auth(support.ALICE), inventory=catalog())
    assert admin.status_code == 200


async def test_without_server_scan_the_page_is_off(
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


async def test_the_confs_in_server_scan_s_shape(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    response = await call(support, gitlab, clock, auth(support.ALICE), inventory=catalog())
    assert response.status_code == 200, response.text
    body = response.json()
    assert list(body) == ["items", "unreadable"]
    assert body["unreadable"] == ["CONF-99"]
    first = body["items"][0]
    assert list(first) == [
        "conf_id",
        "part_number",
        "model",
        "cpu",
        "ram",
        "disks",
        "gpus",
        "gpu_count",
        "gpu_vram_gb",
        "adapters",
        "adapter_count",
    ]
    assert first["conf_id"] == "CONF200"
    assert first["cpu"]["cache_kb"] == {"l1": 2560, "l2": 40960, "l3": 49152}
    assert first["disks"] == [
        {"count": 2, "type": "SSD", "capacity_tb": 0.48},
        {"count": 2, "type": "NVME", "capacity_tb": 1.92},
    ]
    unmapped = next(c for c in body["items"] if c["conf_id"] == "CONF-21")
    assert (unmapped["part_number"], unmapped["ram"]["type"]) == (None, [])
