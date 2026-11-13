"""Settings from the environment, and the composition root's three ways to get a GitLab."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from wingman_core.domain.users import Role, User
from wingman_core.settings import (
    AuthSettings,
    Environment,
    GitBackend,
    GitLabSettings,
    RuntimeSettings,
)
from wingman_day2 import main
from wingman_day2.settings import FAKE_GITLAB_URL, Config, Day2Settings, load_config

SECRET = "settings-test-secret-" + "y" * 32


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """A complete environment for the fake backend; tests adjust it."""
    for name in ("GITLAB_URL", "GITLAB_TOKEN", "WINGMAN_FIXTURES_DIR", "DAY2_GITOPS_BRANCH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WINGMAN_ENVIRONMENT", "test")
    monkeypatch.setenv("WINGMAN_GIT_BACKEND", "fake")
    monkeypatch.setenv("JWT_SECRET_KEY", SECRET)
    monkeypatch.setenv("DAY2_SIGS_GROUP_PATH", "sigs")
    monkeypatch.setenv("DAY1_GITLAB_PROJECT_ID", "gitops-day1/platform-config")
    return monkeypatch


async def get(app: FastAPI, path: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://day2"
    ) as client:
        return await client.get(path)


def test_the_fake_backend_needs_no_gitlab_settings(env: pytest.MonkeyPatch) -> None:
    config = load_config()
    assert config.gitlab is None
    assert config.gitlab_url == FAKE_GITLAB_URL
    assert config.day2.day2_gitops_branch == "main"
    assert config.day2.day1_project == "gitops-day1/platform-config"


def test_the_gitlab_backend_reads_and_requires_the_gitlab_settings(
    env: pytest.MonkeyPatch,
) -> None:
    env.setenv("WINGMAN_GIT_BACKEND", "gitlab")
    with pytest.raises(ValidationError):
        load_config()
    env.setenv("GITLAB_URL", "http://127.0.0.1:9/")
    env.setenv("GITLAB_TOKEN", "local-token")
    config = load_config()
    assert config.gitlab is not None
    assert config.gitlab_url == "http://127.0.0.1:9"


def test_the_fake_backend_is_refused_in_production(env: pytest.MonkeyPatch) -> None:
    env.setenv("WINGMAN_ENVIRONMENT", "production")
    with pytest.raises(ValidationError):
        load_config()


def test_missing_repo_settings_refuse_to_start(env: pytest.MonkeyPatch) -> None:
    env.delenv("DAY2_SIGS_GROUP_PATH")
    with pytest.raises(ValidationError):
        load_config()


def test_the_cache_ttl_is_bounded_to_a_minute(env: pytest.MonkeyPatch) -> None:
    env.setenv("DAY2_CACHE_TTL_SECONDS", "61")
    with pytest.raises(ValidationError):
        load_config()


def test_a_numeric_day1_project_is_an_id() -> None:
    settings = Day2Settings(day2_sigs_group_path="sigs", day1_gitlab_project_id=" 42 ")
    assert settings.day1_project == 42


async def test_create_app_without_a_gitlab_seeds_the_fake_from_the_fixtures(
    env: pytest.MonkeyPatch,
) -> None:
    app = main.create_app(load_config())
    response = await get(app, "/health/ready")
    assert response.json() == {"status": "ready", "checks": {"gitlab": "ok"}}
    assert app.state.day2.info.sigs_group == "sigs"
    teams = await app.state.day2.topology.load()
    assert [t.team.name for t in teams.teams] == ["falcon", "lynx", "orca", "redbull"]


async def test_readiness_asks_gitlab_only_until_it_has_answered_once(
    env: pytest.MonkeyPatch,
) -> None:
    app = main.create_app(load_config())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://day2"
    ) as client:
        ready = [(await client.get("/health/ready")).json() for _ in range(3)]
    assert ready == [{"status": "ready", "checks": {"gitlab": "ok"}}] * 3
    # The sigs group and the day1 project once; then a later GitLab outage is
    # the requests' to report (ADR-0054).
    registry = app.state.metrics.registry
    for operation in ("list_group_projects", "get_project"):
        calls = registry.get_sample_value(
            "wingman_dependency_requests_total",
            {"dependency": "gitlab", "operation": operation, "outcome": "ok"},
        )
        assert calls == 1, operation


async def test_a_session_expires_by_the_clock_the_app_was_given(env: pytest.MonkeyPatch) -> None:
    now = [datetime(2026, 11, 7, tzinfo=UTC)]
    config = load_config()
    app = main.create_app(config, clock=lambda: now[0])
    token = app.state.session_tokens.issue(User("jane", Role.ADMIN))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://day2",
        headers={"authorization": f"Bearer {token}"},
    ) as client:
        assert (await client.get("/api/day2/teams")).status_code == 200
        now[0] += timedelta(hours=config.auth.jwt_expiry_hours, seconds=1)
        assert (await client.get("/api/day2/teams")).status_code == 401


def test_the_module_app_is_built_once_from_the_environment(env: pytest.MonkeyPatch) -> None:
    env.setattr(main, "_app", None)
    first = main.app
    assert isinstance(first, FastAPI)
    assert main.app is first
    with pytest.raises(AttributeError):
        _ = main.nope


async def test_a_gitlab_backend_uses_the_http_adapter_and_reports_an_outage() -> None:
    config = Config(
        runtime=RuntimeSettings(environment=Environment.TEST, git_backend=GitBackend.GITLAB),
        auth=AuthSettings(jwt_secret_key=SECRET),
        day2=Day2Settings(day2_sigs_group_path="sigs", day1_gitlab_project_id="7"),
        gitlab=GitLabSettings(
            url="http://127.0.0.1:9",
            token="local-token",
            connect_timeout_seconds=0.2,
            read_timeout_seconds=0.2,
        ),
    )
    app = main.create_app(config)
    assert app.state.day2.info.gitlab_url == "http://127.0.0.1:9"
    async with app.router.lifespan_context(app):
        response = await get(app, "/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["gitlab"].startswith("error")
