"""Per-team access (ADR-0043): each team is read on its own, and a failed read is unknown."""

from __future__ import annotations

import pytest

from wingman_core.domain.errors import GitUnavailableError
from wingman_core.domain.git import AccessLevel
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day2.application.services import Day2Services
from wingman_day2.domain.errors import TeamReadOnlyError
from wingman_day2.domain.teams import Team, UnknownAccess

UNAVAILABLE = "GET /api/v4/projects/3: 503 Service Unavailable"


async def _teams(services: Day2Services) -> dict[str, Team]:
    return {s.team.name: s.team for s in (await services.topology.load()).teams}


def _fail_for(gitlab: InMemoryGitLab, monkeypatch: pytest.MonkeyPatch, project_id: int) -> None:
    real = gitlab.access_level

    async def access_level(pid: int) -> AccessLevel:
        if pid == project_id:
            raise GitUnavailableError(UNAVAILABLE)
        return await real(pid)

    monkeypatch.setattr(gitlab, "access_level", access_level)


async def test_one_teams_failed_access_read_leaves_the_other_teams(
    services: Day2Services, gitlab: InMemoryGitLab, monkeypatch: pytest.MonkeyPatch
) -> None:
    teams = await _teams(services)
    _fail_for(gitlab, monkeypatch, teams["lynx"].project.id)
    access = await services.access.of_all(list(teams.values()))
    assert {name: (a.writable, a.level.role) for name, a in access.items()} == {
        "falcon": (True, "owner"),
        "lynx": (False, "unknown"),
        "orca": (False, "reporter"),
        "redbull": (True, "owner"),
    }
    lynx = access["lynx"]
    assert lynx.level == UnknownAccess(UNAVAILABLE) and int(lynx.level) == 0
    assert lynx.reason == (
        f"Wingman could not read its access to sigs/lynx ({UNAVAILABLE}): "
        "lynx is read-only until it can."
    )


async def test_a_team_whose_access_is_unknown_is_refused_every_write(
    services: Day2Services, gitlab: InMemoryGitLab, monkeypatch: pytest.MonkeyPatch
) -> None:
    lynx = (await _teams(services))["lynx"]
    _fail_for(gitlab, monkeypatch, lynx.project.id)
    with pytest.raises(TeamReadOnlyError) as refused:
        await services.access.require_write(lynx)
    assert refused.value.detail.startswith("Wingman could not read its access to sigs/lynx")
    assert refused.value.details == {
        "team": "lynx",
        "project": "sigs/lynx",
        "access_level": 0,
        "access_role": "unknown",
        "required_level": 30,
    }


async def test_a_failed_access_read_is_not_kept(
    services: Day2Services, gitlab: InMemoryGitLab, monkeypatch: pytest.MonkeyPatch
) -> None:
    lynx = (await _teams(services))["lynx"]
    with monkeypatch.context() as patch:
        _fail_for(gitlab, patch, lynx.project.id)
        assert not (await services.access.of(lynx)).writable
    # GitLab answers again: the next read asks it, inside the TTL a kept answer would have.
    assert (await services.access.of(lynx)).level is AccessLevel.OWNER
