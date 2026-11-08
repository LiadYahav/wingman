"""The composition root: settings in, adapters built, use cases wired, app out (ADR-0001).

    uvicorn wingman_day2.main:app --port 8002

``app`` is built on first access (PEP 562), so importing this module (tests do)
reads no environment. ``WINGMAN_GIT_BACKEND=fake`` serves an in-memory GitLab
seeded from ``dev/gitlab-fixtures``, for local development and E2E; settings
refuse it in production (ADR-0009).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from fastapi import FastAPI
from prometheus_client import CollectorRegistry

from wingman_core.infrastructure.cache import TtlCache
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.infrastructure.gitlab import GitLabHttpAdapter
from wingman_core.infrastructure.gitlab.http import build_client
from wingman_core.infrastructure.session_tokens import SessionTokens
from wingman_core.observability.instrumented_gitlab import InstrumentedGitLab
from wingman_core.observability.metrics import WingmanMetrics
from wingman_core.ports.clock import Clock, system_clock
from wingman_core.ports.gitlab import GitLabPort
from wingman_core.settings import GitBackend
from wingman_core.web.app_factory import create_base_app
from wingman_day2.api.v1 import router
from wingman_day2.api.v1.errors import register_day2_errors
from wingman_day2.application.services import Day2Services
from wingman_day2.infrastructure.repositories import (
    GitLabChartRepository,
    GitLabDay1Repository,
    GitLabSigsRepository,
)
from wingman_day2.settings import FAKE_GITLAB_URL, Config, load_config


def seeded_fake(config: Config, clock: Clock) -> InMemoryGitLab:
    """An in-memory GitLab holding the fixture repos, chart URLs pointing at itself."""
    from wingman_core.testing.fixtures import (
        default_fixture_root,
        load_fixture_projects,
        seed_fake,
    )

    gitlab = InMemoryGitLab(clock=clock, base_url=FAKE_GITLAB_URL)
    root = config.runtime.fixtures_dir or default_fixture_root()
    seed_fake(gitlab, load_fixture_projects(root, substitutions={"GITLAB_URL": FAKE_GITLAB_URL}))
    return gitlab


def create_app(
    config: Config | None = None,
    *,
    gitlab: GitLabPort | None = None,
    clock: Clock = system_clock,
    registry: CollectorRegistry | None = None,
) -> FastAPI:
    """The day2 service. Tests pass ``config`` and ``gitlab``; production reads the environment."""
    config = config or load_config()
    metrics = WingmanMetrics(
        registry or CollectorRegistry(),
        component="day2",
        version=config.runtime.version,
        commit=config.runtime.commit,
    )
    client: httpx.AsyncClient | None = None
    if gitlab is None:
        if config.runtime.git_backend is GitBackend.FAKE or config.gitlab is None:
            gitlab = seeded_fake(config, clock)
        else:
            client = build_client(config.gitlab)
            gitlab = GitLabHttpAdapter(client)
    port = InstrumentedGitLab(gitlab, metrics)
    cache = TtlCache()
    ttl = config.day2.day2_cache_ttl_seconds
    branch = config.day2.day2_gitops_branch
    sigs = GitLabSigsRepository(
        port, cache, group=config.day2.day2_sigs_group_path, branch=branch, ttl=ttl
    )
    day1 = GitLabDay1Repository(
        port, cache, project=config.day2.day1_project, branch=branch, ttl=ttl
    )
    charts = GitLabChartRepository(port, cache, base_url=config.gitlab_url, ttl=ttl)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if client is not None:
            await client.aclose()

    async def gitlab_ready() -> None:
        await port.list_group_projects(config.day2.day2_sigs_group_path)
        await port.get_project(config.day2.day1_project)

    app = create_base_app(
        title="Wingman day2",
        version=config.runtime.version,
        metrics=metrics,
        session_tokens=SessionTokens(
            config.auth.jwt_secret_key.get_secret_value(),
            ttl=timedelta(hours=config.auth.jwt_expiry_hours),
        ),
        readiness={"gitlab": gitlab_ready},
        lifespan=lifespan,
    )
    app.state.day2 = Day2Services.build(
        gitlab=port,
        sigs=sigs,
        day1=day1,
        charts=charts,
        clock=clock,
        gitlab_url=config.gitlab_url,
    )
    register_day2_errors(app)
    app.include_router(router)
    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> object:
    """``app``, built from the environment on first access (``uvicorn wingman_day2.main:app``)."""
    global _app
    if name != "app":
        raise AttributeError(name)
    if _app is None:
        _app = create_app()
    return _app
