"""Shared fixtures: an in-memory GitLab seeded from ``dev/gitlab-fixtures``, the app, users.

Tests run with ``--import-mode=importlib``, so they cannot import this module;
everything shared is a fixture.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from functools import cache

import httpx
import pytest
from fastapi import FastAPI

from wingman_core.domain.users import Role, User
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.infrastructure.session_tokens import SessionTokens
from wingman_core.settings import AuthSettings, Environment, GitBackend, RuntimeSettings
from wingman_core.testing.fixtures import (
    FixtureProject,
    default_fixture_root,
    load_fixture_projects,
    seed_fake,
)
from wingman_day2.application.services import Day2Services
from wingman_day2.infrastructure.repositories import (
    GitLabChartRepository,
    GitLabDay1Repository,
    GitLabSigsRepository,
)
from wingman_day2.main import create_app
from wingman_day2.settings import FAKE_GITLAB_URL, Config, Day2Settings

SECRET = "test-secret-" + "x" * 32


class Clock:
    """A clock that ticks one second per reading, from a fixed start."""

    def __init__(self) -> None:
        self.now = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@cache
def _fixture_projects() -> tuple[FixtureProject, ...]:
    return tuple(
        load_fixture_projects(default_fixture_root(), substitutions={"GITLAB_URL": FAKE_GITLAB_URL})
    )


@pytest.fixture
def fixture_projects() -> tuple[FixtureProject, ...]:
    """The fixture repos, with chart URLs pointing at the fake."""
    return _fixture_projects()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def gitlab(clock: Clock, fixture_projects: tuple[FixtureProject, ...]) -> InMemoryGitLab:
    fake = InMemoryGitLab(clock=clock, base_url=FAKE_GITLAB_URL)
    seed_fake(fake, list(fixture_projects))
    return fake


@pytest.fixture
def cache() -> TtlCache:
    return TtlCache()


@pytest.fixture
def sigs(gitlab: InMemoryGitLab, cache: TtlCache) -> GitLabSigsRepository:
    return GitLabSigsRepository(gitlab, cache, group="sigs", branch="main", ttl=30)


@pytest.fixture
def day1(gitlab: InMemoryGitLab, cache: TtlCache) -> GitLabDay1Repository:
    return GitLabDay1Repository(
        gitlab, cache, project="gitops-day1/platform-config", branch="main", ttl=30
    )


@pytest.fixture
def charts(gitlab: InMemoryGitLab, cache: TtlCache) -> GitLabChartRepository:
    return GitLabChartRepository(gitlab, cache, base_url=FAKE_GITLAB_URL, ttl=30)


@pytest.fixture
def services(
    gitlab: InMemoryGitLab,
    sigs: GitLabSigsRepository,
    day1: GitLabDay1Repository,
    charts: GitLabChartRepository,
    clock: Clock,
) -> Day2Services:
    return Day2Services.build(
        gitlab=gitlab, sigs=sigs, day1=day1, charts=charts, clock=clock, gitlab_url=FAKE_GITLAB_URL
    )


@pytest.fixture
def config() -> Config:
    """A configuration for the fake backend."""
    return Config(
        runtime=RuntimeSettings(environment=Environment.TEST, git_backend=GitBackend.FAKE),
        auth=AuthSettings(jwt_secret_key=SECRET),
        day2=Day2Settings(
            day2_sigs_group_path="sigs", day1_gitlab_project_id="gitops-day1/platform-config"
        ),
        gitlab=None,
    )


@pytest.fixture
def app(config: Config, gitlab: InMemoryGitLab, clock: Clock) -> FastAPI:
    return create_app(config, gitlab=gitlab, clock=clock)


@pytest.fixture
def jane_user() -> User:
    return User("jane", Role.ADMIN)


@pytest.fixture
def bob_user() -> User:
    return User("bob", Role.ADMIN)


ClientFor = Callable[[User | None], httpx.AsyncClient]


@pytest.fixture
async def client_for(app: FastAPI) -> AsyncIterator[ClientFor]:
    """A factory of API clients logged in as a user (``None``: no token)."""
    # The app's own tokens: they run on its injected clock, as the services do.
    tokens: SessionTokens = app.state.session_tokens
    clients: list[httpx.AsyncClient] = []

    def make(user: User | None) -> httpx.AsyncClient:
        headers = {"authorization": f"Bearer {tokens.issue(user)}"} if user else {}
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://day2", headers=headers
        )
        clients.append(client)
        return client

    yield make
    for client in clients:
        await client.aclose()


@pytest.fixture
def jane(client_for: ClientFor, jane_user: User) -> httpx.AsyncClient:
    """An admin."""
    return client_for(jane_user)


@pytest.fixture
def bob(client_for: ClientFor, bob_user: User) -> httpx.AsyncClient:
    """Another admin."""
    return client_for(bob_user)


@pytest.fixture
def vic(client_for: ClientFor) -> httpx.AsyncClient:
    """A viewer."""
    return client_for(User("vic", Role.VIEWER))


@pytest.fixture
def anonymous(client_for: ClientFor) -> httpx.AsyncClient:
    """No token at all."""
    return client_for(None)
