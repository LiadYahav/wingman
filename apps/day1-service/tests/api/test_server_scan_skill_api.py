"""The Claude page's routes (docs/notes/2026-11-13-server-scan-area-api.md §12).

server-scan's skill in its shape with where server-scan is for people and
the token line its zip names, and the zip with that address written in:
admins only, 404 when server-scan carries no skill, 501 when off, 502 when
server-scan fails or refuses. Built on the fake fleet and its skill fixture.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from wingman_core.domain.users import User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.domain.errors import ServerScanDeniedError
from wingman_day1.domain.server_scan_skill import Skill
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.fake_server_scan_skill import default_skill_dir, load_skill
from wingman_day1.ports import ServerInventory

Auth = Callable[[User], dict[str, str]]
SKILL = "/api/day1/server-scan/skill"
DOWNLOAD = f"{SKILL}/download"
UI = "https://server-scan.example"
SKILL_FIELDS = {
    "name",
    "description",
    "when_to_use",
    "allowed_tools",
    "version",
    "updated_at",
    "files",
    "server_scan_url",
    "token_line",
}


def client(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    inventory: ServerInventory | None,
    **settings: object,
) -> httpx.AsyncClient:
    app = support.build_app(
        gitlab=gitlab,
        hub=None,
        identity=None,
        day2=FakeDay2Addons(),
        clock=clock,
        inventory=inventory,
        **settings,
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://day1.test")


def with_skill() -> FakeServerInventory:
    return FakeServerInventory(skill=load_skill(default_skill_dir()))


class DeniedFleet(FakeServerInventory):
    async def skill(self) -> Skill:
        raise ServerScanDeniedError(
            "server-scan refused Wingman's token (401) reading the Claude skill: "
            "check SERVER_SCAN_TOKEN"
        )


async def test_only_admins_read_the_skill(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, with_skill()) as http:
        for path in (SKILL, DOWNLOAD):
            assert (await http.get(path)).status_code == 401
            viewer = await http.get(path, headers=auth(support.VIEWER))
            assert (viewer.status_code, viewer.json()["code"]) == (403, "FORBIDDEN")


async def test_the_skill_is_server_scans_shape_with_its_address_and_token_line(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, with_skill(), SERVER_SCAN_UI_URL=UI) as http:
        response = await http.get(SKILL, headers=auth(support.ALICE))
    assert response.status_code == 200
    body = response.json()
    assert set(body) == SKILL_FIELDS
    assert (body["name"], body["server_scan_url"], body["token_line"]) == (
        "server-scan-api",
        UI,
        "AUDITOR_TOKEN",
    )
    assert [f["path"] for f in body["files"]] == ["SKILL.md", "references/endpoints.md"]
    assert set(body["files"][0]) == {"path", "content"}


@pytest.mark.parametrize(
    ("settings", "line"),
    [({"server_scan_token": "viewer"}, "VIEWER_TOKEN"), ({}, "AUDITOR_TOKEN")],
)
async def test_the_token_line_is_the_one_server_scan_writes_for_wingman(
    support: Any,
    gitlab: InMemoryGitLab,
    clock: Any,
    auth: Auth,
    settings: dict[str, str],
    line: str,
) -> None:
    async with client(support, gitlab, clock, with_skill(), **settings) as http:
        body = (await http.get(SKILL, headers=auth(support.ALICE))).json()
    assert body["token_line"] == line


async def test_the_fake_fleets_server_scan_has_the_fake_address(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, with_skill()) as http:
        body = (await http.get(SKILL, headers=auth(support.ALICE))).json()
    assert body["server_scan_url"] == "http://server-scan.example"


async def test_the_download_is_server_scans_zip_with_its_address(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, with_skill(), SERVER_SCAN_UI_URL=f"{UI}/") as http:
        response = await http.get(DOWNLOAD, headers=auth(support.ALICE))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == 'attachment; filename="server-scan-api.zip"'
    assert response.headers["cache-control"] == "no-cache"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        text = archive.read("server-scan-api/SKILL.md").decode()
    assert f"BASE_URL={UI}\n" in text


async def test_no_skill_is_404(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, FakeServerInventory()) as http:
        for path in (SKILL, DOWNLOAD):
            response = await http.get(path, headers=auth(support.ALICE))
            assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
            assert "carries no Claude Code skill" in response.json()["detail"]


async def test_without_server_scan_the_skill_is_501(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    async with client(support, gitlab, clock, None) as http:
        for path in (SKILL, DOWNLOAD):
            response = await http.get(path, headers=auth(support.ALICE))
            assert (response.status_code, response.json()["code"]) == (501, "FEATURE_DISABLED")
            assert "SERVER_SCAN_URL" in response.json()["detail"]


async def test_server_scan_failing_or_refusing_is_502(
    support: Any, gitlab: InMemoryGitLab, clock: Any, auth: Auth
) -> None:
    down = FakeServerInventory(skill=load_skill(default_skill_dir()), unavailable=True)
    async with client(support, gitlab, clock, down) as http:
        download = await http.get(DOWNLOAD, headers=auth(support.ALICE))
    async with client(support, gitlab, clock, DeniedFleet()) as http:
        refused = await http.get(SKILL, headers=auth(support.ALICE))
    assert (download.status_code, download.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    assert (refused.status_code, refused.json()["code"]) == (502, "DEPENDENCY_UNAVAILABLE")
    assert "SERVER_SCAN_TOKEN" in refused.json()["detail"]
