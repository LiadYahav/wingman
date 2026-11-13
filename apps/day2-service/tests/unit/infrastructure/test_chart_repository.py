"""Chart repo lookups: answered stale while one read refreshes them (ADR-0041).

The add-on list looks up every chart repo's project and branches. Before,
those lookups had a plain TTL, so the first list after each TTL waited on
GitLab for all of them.
"""

from __future__ import annotations

import asyncio
import inspect
from collections import Counter
from typing import Any

import pytest

from wingman_core.domain.errors import GitUnavailableError
from wingman_core.domain.git import Branch, RepoPath
from wingman_core.infrastructure.cache import MAX_AGE, TtlCache
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.infrastructure.snapshots import RepoSnapshots
from wingman_day2.application.catalog import CatalogEntry
from wingman_day2.application.services import Day2Services
from wingman_day2.infrastructure.repositories import (
    GitLabChartRepository,
    GitLabDay1Repository,
    GitLabSigsRepository,
)
from wingman_day2.settings import FAKE_GITLAB_URL

TTL = 15.0
ROLES = f"{FAKE_GITLAB_URL}/helm-charts/cluster-roles.git"


class Seconds:
    """The cache's clock, moved by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Gate:
    """Counts every GitLab call and, while closed, holds each one until it opens.

    A read that awaits GitLab while the gate is closed never finishes, so
    ``asyncio.wait_for`` turns "it waited on GitLab" into a failure.
    """

    def __init__(self, gitlab: InMemoryGitLab, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: Counter[str] = Counter()
        self._open = asyncio.Event()
        self._open.set()
        for name in dir(InMemoryGitLab):
            method = getattr(gitlab, name)
            if name.startswith("_") or not inspect.iscoroutinefunction(method):
                continue

            async def gated(
                *args: object, _name: str = name, _method: Any = method, **kw: Any
            ) -> Any:
                self.calls[_name] += 1
                await self._open.wait()
                return await _method(*args, **kw)

            monkeypatch.setattr(gitlab, name, gated)

    def close(self) -> None:
        self._open.clear()
        self.calls.clear()

    def open(self) -> None:
        self._open.set()


async def settle() -> None:
    """Let the background refreshes run until they finish or reach the gate."""
    for _ in range(10):
        await asyncio.sleep(0)


@pytest.fixture
def seconds() -> Seconds:
    return Seconds()


@pytest.fixture
def gate(gitlab: InMemoryGitLab, monkeypatch: pytest.MonkeyPatch) -> Gate:
    return Gate(gitlab, monkeypatch)


@pytest.fixture
def ttl_cache(seconds: Seconds) -> TtlCache:
    return TtlCache(clock=seconds)


@pytest.fixture
def chart_repos(gitlab: InMemoryGitLab, ttl_cache: TtlCache) -> GitLabChartRepository:
    return GitLabChartRepository(gitlab, ttl_cache, base_url=FAKE_GITLAB_URL, ttl=TTL)


@pytest.fixture
def day2(
    gitlab: InMemoryGitLab, ttl_cache: TtlCache, chart_repos: GitLabChartRepository, clock: Any
) -> Day2Services:
    snapshots = RepoSnapshots(gitlab, ttl_cache, ttl=TTL)
    return Day2Services.build(
        gitlab=gitlab,
        sigs=GitLabSigsRepository(
            gitlab, ttl_cache, snapshots, group="sigs", branch="main", ttl=TTL
        ),
        day1=GitLabDay1Repository(
            gitlab,
            ttl_cache,
            snapshots,
            project="gitops-day1/platform-config",
            branch="main",
            ttl=TTL,
        ),
        charts=chart_repos,
        clock=clock,
        gitlab_url=FAKE_GITLAB_URL,
    )


def versions(entries: list[CatalogEntry]) -> dict[tuple[str, str], tuple[str, ...] | None]:
    return {(e.team, e.chart): e.versions for e in entries}


async def test_past_the_ttl_the_addon_list_answers_at_once_and_each_lookup_refreshes_once(
    day2: Day2Services, gitlab: InMemoryGitLab, gate: Gate, seconds: Seconds
) -> None:
    before = await day2.catalog.entries()
    cold = Counter({k: v for k, v in gate.calls.items() if k in ("get_project", "list_branches")})
    assert cold["list_branches"] > 1  # several chart repos, so the shared refresh means something
    roles = await gitlab.get_project("helm-charts/cluster-roles")
    gitlab.create_project_branch(roles.id, "3.0.0", {"values.yaml": "a: 1\n"})

    gate.close()
    seconds.now += TTL + 1
    pages = await asyncio.wait_for(
        asyncio.gather(*(day2.catalog.entries() for _ in range(3))), timeout=2
    )
    assert all(versions(page) == versions(before) for page in pages)  # no read waited on GitLab
    await settle()
    refreshed = Counter({k: gate.calls[k] for k in cold})
    assert refreshed == cold  # one refresh per lookup, shared by the three pages

    gate.open()
    await settle()
    gate.close()  # the next list is answered from the refreshed lookups, without GitLab
    after = versions(await asyncio.wait_for(day2.catalog.entries(), timeout=2))
    assert after[("redbull", "cluster-roles")] == ("main", "3.0.0", "2.1.5-hotfix", "2.0.0")
    gate.open()
    await settle()


async def test_a_values_file_is_answered_stale_while_one_read_refreshes_it(
    chart_repos: GitLabChartRepository, gate: Gate, seconds: Seconds
) -> None:
    project = await chart_repos.resolve(ROLES)
    assert project is not None
    first = await chart_repos.values(project, "2.0.0", RepoPath.root())
    gate.close()
    seconds.now += TTL + 1
    reads = asyncio.gather(
        *(chart_repos.values(project, "2.0.0", RepoPath.root()) for _ in range(5))
    )
    assert await asyncio.wait_for(reads, timeout=2) == [first] * 5
    await settle()
    assert gate.calls == Counter(read_file=1)
    gate.open()
    await settle()


async def test_a_moved_chart_repo_is_seen_once_the_refresh_has_read_it(
    chart_repos: GitLabChartRepository, gitlab: InMemoryGitLab, seconds: Seconds
) -> None:
    before = await chart_repos.resolve(ROLES)
    assert before is not None
    gitlab.rename_project(before.id, "helm-charts/cluster-roles-operator")
    seconds.now += TTL + 1
    assert await chart_repos.resolve(ROLES) == before  # answered stale; the refresh starts
    await settle()
    after = await chart_repos.resolve(ROLES)
    assert after is not None and after.path_with_namespace == "helm-charts/cluster-roles-operator"


async def test_no_such_chart_repo_is_an_answer_refreshed_like_a_project(
    chart_repos: GitLabChartRepository, gitlab: InMemoryGitLab, seconds: Seconds
) -> None:
    url = f"{FAKE_GITLAB_URL}/helm-charts/not-yet.git"
    assert await chart_repos.resolve(url) is None
    created = gitlab.create_project("helm-charts/not-yet", {"values.yaml": "a: 1\n"})
    assert await chart_repos.resolve(url) is None  # within the TTL: kept
    seconds.now += TTL + 1
    assert await chart_repos.resolve(url) is None  # answered stale; the refresh starts
    await settle()
    assert await chart_repos.resolve(url) == created


async def test_an_unreachable_gitlab_keeps_the_lookup_for_the_minute_then_fails_the_list(
    day2: Day2Services,
    gitlab: InMemoryGitLab,
    seconds: Seconds,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    before = versions(await day2.catalog.entries())

    async def unreachable(project_id: int) -> list[Branch]:
        raise GitUnavailableError(f"GitLab unreachable on GET /projects/{project_id}: ConnectError")

    monkeypatch.setattr(gitlab, "list_branches", unreachable)
    seconds.now += TTL + 1
    assert versions(await day2.catalog.entries()) == before  # within the minute: the last answer
    await settle()
    assert "refreshing day2:chart:" in caplog.text  # the failed refresh is logged, not kept
    seconds.now += MAX_AGE
    with pytest.raises(GitUnavailableError):
        await day2.catalog.entries()
