"""Per-team access through HTTP when GitLab does not answer one team's (ADR-0043)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from wingman_core.domain.errors import GitUnavailableError
from wingman_core.domain.git import AccessLevel
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab

UNAVAILABLE = "GET /api/v4/projects/3: 503 Service Unavailable"


def ok(response: httpx.Response) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


async def test_one_teams_unreadable_access_makes_only_that_team_read_only(
    jane: httpx.AsyncClient, gitlab: InMemoryGitLab, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = gitlab.access_level
    lynx = (await gitlab.get_project("sigs/lynx")).id

    async def access_level(project_id: int) -> AccessLevel:
        if project_id == lynx:
            raise GitUnavailableError(UNAVAILABLE)
        return await real(project_id)

    monkeypatch.setattr(gitlab, "access_level", access_level)
    teams = {t["name"]: t for t in ok(await jane.get("/api/day2/teams"))}
    assert {n: (t["writable"], t["access_role"]) for n, t in teams.items()} == {
        "falcon": (True, "owner"),
        "lynx": (False, "unknown"),
        "orca": (False, "reporter"),
        "redbull": (True, "owner"),
    }
    assert teams["lynx"]["access_level"] == 0
    assert teams["lynx"]["read_only_reason"] == (
        f"Wingman could not read its access to sigs/lynx ({UNAVAILABLE}): "
        "lynx is read-only until it can."
    )
    assert ok(await jane.get("/api/day2/teams/lynx")) == teams["lynx"]
    entries = ok(await jane.get("/api/day2/addons"))
    assert {e["team"] for e in entries if not e["writable"]} == {"lynx", "orca"}
    assert {e["team"] for e in entries} == set(teams)
    defaults = ok(await jane.get("/api/day2/fleet-defaults"))
    assert {(d["team"], d["writable"]) for d in defaults} == {
        ("falcon", True),
        ("lynx", False),
        ("orca", False),
        ("redbull", True),
    }

    refused = await jane.put("/api/day2/addons/lynx/backup", json={"sync": {"auto_sync": False}})
    assert refused.status_code == 403, refused.text
    body = refused.json()
    assert body["code"] == "TEAM_READ_ONLY"
    assert (body["details"]["access_role"], body["details"]["access_level"]) == ("unknown", 0)

    monkeypatch.setattr(gitlab, "access_level", real)
    assert ok(await jane.get("/api/day2/teams/lynx"))["writable"] is True
