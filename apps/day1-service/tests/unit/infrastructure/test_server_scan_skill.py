"""The Claude page: server-scan's skill and its zip (ADR-0048, 3.29.0).

The adapter against server-scan's answers (MockTransport), in the shape its
``backend/app/api/v1/skill.py`` sends at 92146d3: the skill read and typed,
malformed answers refused, no skill a 404 in server-scan's words, the zip
passed on with the address asked for, the viewer token on both, the metrics.
The cache keeps the skill for its TTL and never the zip; the fake reads and
zips its fixture as server-scan does; the token line follows server-scan's
rule (docs/notes/2026-11-13-server-scan-area-api.md §12).
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import (
    ServerScanDeniedError,
    ServerScanSkillMissingError,
    ServerScanUnavailableError,
)
from wingman_day1.domain.server_scan_skill import Skill, SkillZip, token_line
from wingman_day1.infrastructure.cached_server_scan import CachedServerInventory
from wingman_day1.infrastructure.fake_fleet import FakeServerInventory
from wingman_day1.infrastructure.fake_server_scan_skill import (
    default_skill_dir,
    load_skill,
    zip_skill,
)
from wingman_day1.infrastructure.server_scan import HttpServerInventory

VIEWER = "server-scan-viewer-token-never-shown-0001"
UI = "https://server-scan.example"


def server_scan_skill(**over: Any) -> dict[str, Any]:
    """server-scan's ``SkillResponse``, as its ``GET /api/v1/skill`` sends it."""
    return {
        "name": "server-scan-api",
        "description": 'Queries the Server Scan REST API ("all Dell servers in tlv").',
        "when_to_use": "Also for a server's BMC address.",
        "allowed_tools": "Bash(curl *) Bash(jq *)",
        "version": "0123456789ab",
        "updated_at": "2026-11-01T08:00:00Z",
        "files": [
            {"path": "SKILL.md", "content": "---\nname: server-scan-api\n---\n# Server Scan API\n"},
            {"path": "references/endpoints.md", "content": "# Endpoints\n"},
        ],
        **over,
    }


def a_zip(name: str = "server-scan-api") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(f"{name}/SKILL.md", "BASE_URL=https://server-scan.example\n")
    return out.getvalue()


def zipped(content: bytes, name: str = "server-scan-api") -> httpx.Response:
    disposition = f'attachment; filename="{name}.zip"'
    headers = {"content-type": "application/zip", "content-disposition": disposition}
    return httpx.Response(200, content=content, headers=headers)


def make(
    *answers: httpx.Response | Exception, metrics: WingmanMetrics | None = None
) -> tuple[HttpServerInventory, list[httpx.Request]]:
    sent: list[httpx.Request] = []
    queue = list(answers)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    inventory = HttpServerInventory(
        base_url="http://server-scan-api.inventory.svc:8000",
        token=VIEWER,
        admin_token="server-scan-admin-token-never-shown-0003",
        auditor_token="server-scan-auditor-token-never-shown-0002",
        metrics=metrics,
        transport=httpx.MockTransport(handler),
        timer=iter(range(1000)).__next__,
    )
    return inventory, sent


# ── The skill ────────────────────────────────────────────────────────────────


async def test_the_skill_is_read_typed_with_the_viewer_token() -> None:
    inventory, sent = make(httpx.Response(200, json=server_scan_skill()))
    skill = await inventory.skill()
    (request,) = sent
    assert (request.method, request.url.path) == ("GET", "/api/v1/skill")
    assert request.headers["authorization"] == f"Bearer {VIEWER}"
    assert (skill.name, skill.version) == ("server-scan-api", "0123456789ab")
    assert [f.path for f in skill.files] == ["SKILL.md", "references/endpoints.md"]
    assert skill.updated_at.year == 2026


@pytest.mark.parametrize(
    "broken",
    [
        server_scan_skill(files=[{"path": "SKILL.md"}]),
        server_scan_skill(version=12),
        server_scan_skill(updated_at="yesterday"),
        {"name": "server-scan-api"},
        [],
    ],
)
async def test_a_malformed_skill_is_unavailable_never_a_blank(broken: object) -> None:
    inventory, _ = make(httpx.Response(200, json=broken))
    with pytest.raises(ServerScanUnavailableError, match="malformed Claude skill"):
        await inventory.skill()


async def test_no_skill_is_its_own_error_in_server_scans_words() -> None:
    detail = {"code": "NOT_FOUND", "detail": "This deployment carries no Claude Code skill."}
    inventory, _ = make(httpx.Response(404, json=detail), httpx.Response(404, text="nope"))
    with pytest.raises(ServerScanSkillMissingError, match="carries no Claude Code skill"):
        await inventory.skill()
    with pytest.raises(ServerScanSkillMissingError, match="carries no Claude Code skill"):
        await inventory.skill_zip(UI)


async def test_a_refused_token_names_its_setting() -> None:
    inventory, _ = make(httpx.Response(401, json={}))
    with pytest.raises(ServerScanDeniedError, match="SERVER_SCAN_TOKEN"):
        await inventory.skill()


# ── The zip ──────────────────────────────────────────────────────────────────


async def test_the_zip_asks_for_the_address_and_is_passed_on_as_it_is() -> None:
    content = a_zip()
    inventory, sent = make(zipped(content))
    archive = await inventory.skill_zip(UI)
    (request,) = sent
    assert request.url.path == "/api/v1/skill/download"
    assert request.url.params["base_url"] == UI
    assert request.headers["authorization"] == f"Bearer {VIEWER}"
    assert (archive.content, archive.filename) == (content, "server-scan-api.zip")


async def test_the_zip_keeps_server_scans_name_only_when_it_is_a_name() -> None:
    inventory, _ = make(zipped(a_zip("fleet-skill"), "fleet-skill"), zipped(a_zip(), "x\r\ny"))
    assert (await inventory.skill_zip(UI)).filename == "fleet-skill.zip"
    assert (await inventory.skill_zip(UI)).filename == "server-scan-api.zip"


async def test_an_answer_that_is_not_a_zip_is_unavailable() -> None:
    inventory, _ = make(zipped(b"<html>login</html>"))
    with pytest.raises(ServerScanUnavailableError, match="not a zip"):
        await inventory.skill_zip(UI)


async def test_a_refused_address_names_the_setting() -> None:
    inventory, _ = make(httpx.Response(422, json={"detail": "base_url must be a plain address"}))
    with pytest.raises(ServerScanUnavailableError, match="SERVER_SCAN_UI_URL"):
        await inventory.skill_zip("https://server_scan.example")


async def test_both_reads_are_measured() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    inventory, _ = make(
        httpx.Response(200, json=server_scan_skill()),
        httpx.Response(404, json={}),
        zipped(a_zip()),
        httpx.ConnectError("down"),
        metrics=metrics,
    )
    await inventory.skill()
    with pytest.raises(ServerScanSkillMissingError):
        await inventory.skill()
    await inventory.skill_zip(UI)
    with pytest.raises(ServerScanUnavailableError):
        await inventory.skill_zip(UI)

    def count(operation: str, outcome: str) -> float | None:
        labels = {"dependency": "server_scan", "operation": operation, "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert (count("get_skill", "ok"), count("get_skill", "not_found")) == (1, 1)
    assert (count("download_skill", "ok"), count("download_skill", "unavailable")) == (1, 1)


# ── The cache, the fake and the token line ───────────────────────────────────


class CountingFleet(FakeServerInventory):
    def __init__(self) -> None:
        super().__init__(skill=load_skill(default_skill_dir()))
        self.reads: list[str] = []

    async def skill(self) -> Skill:
        self.reads.append("skill")
        return await super().skill()

    async def skill_zip(self, base_url: str) -> SkillZip:
        self.reads.append("zip")
        return await super().skill_zip(base_url)


async def test_the_cache_keeps_the_skill_for_its_ttl_and_never_the_zip() -> None:
    clock = [0.0]
    inner = CountingFleet()
    cached = CachedServerInventory(inner, TtlCache(clock=lambda: clock[0]), ttl=300, skill_ttl=60)
    for _ in range(2):
        await cached.skill()
        await cached.skill_zip(UI)
    clock[0] = 61.0
    await cached.skill()
    assert inner.reads == ["skill", "zip", "zip", "skill"]


def test_the_fake_reads_its_skill_as_server_scan_reads_its_own() -> None:
    skill = load_skill(default_skill_dir())
    assert skill.name == "server-scan-api"
    assert skill.allowed_tools == "Bash(curl *) Bash(jq *)"
    assert '"all Dell servers in site1"' in skill.description
    assert skill.when_to_use.startswith("Also for")
    assert [f.path for f in skill.files] == ["SKILL.md", "references/endpoints.md"]
    assert len(skill.version) == 12


def test_the_fake_zip_writes_the_address_and_never_a_token() -> None:
    archive = zip_skill(load_skill(default_skill_dir()), UI)
    with zipfile.ZipFile(io.BytesIO(archive.content)) as opened:
        names = opened.namelist()
        text = opened.read("server-scan-api/SKILL.md").decode()
    assert names == ["server-scan-api/SKILL.md", "server-scan-api/references/endpoints.md"]
    assert f"BASE_URL={UI}\n" in text
    assert "AUDITOR_TOKEN=REPLACE_WITH_AUDITOR_TOKEN" in text
    assert archive.filename == "server-scan-api.zip"


async def test_a_fake_without_a_skill_carries_none() -> None:
    with pytest.raises(ServerScanSkillMissingError):
        await FakeServerInventory().skill()


def test_the_token_line_is_server_scans_rule_for_wingman_as_the_caller() -> None:
    assert token_line(viewer_token=True) == "VIEWER_TOKEN"
    assert token_line(viewer_token=False) == "AUDITOR_TOKEN"
