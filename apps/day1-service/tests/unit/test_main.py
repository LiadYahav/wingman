"""The composition root: which adapters each configuration builds, and how the app is wired."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import CollectorRegistry
from pydantic import SecretStr

import wingman_day1.main as main
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.observability.instrumented_gitlab import InstrumentedGitLab
from wingman_core.observability.metrics import WingmanMetrics
from wingman_core.settings import AuthSettings, Environment, GitBackend, RuntimeSettings
from wingman_core.testing.fixtures import default_fixture_root, load_fixture_projects
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons
from wingman_day1.infrastructure.hub_api import HttpHubApi
from wingman_day1.infrastructure.openshift_oauth import OpenShiftOAuth
from wingman_day1.main import Adapters, build_adapters, create_app
from wingman_day1.settings import Day1Settings

DEV_SECRET = "d" * 40
FAKE = RuntimeSettings(environment=Environment.DEVELOPMENT, git_backend=GitBackend.FAKE)
REAL = RuntimeSettings(environment=Environment.PRODUCTION, git_backend=GitBackend.GITLAB)


def metrics() -> WingmanMetrics:
    return WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")


def settings(**values: object) -> Day1Settings:
    base: dict[str, object] = {
        "day1_gitlab_project_id": "gitops-day1/platform-config",
        "specs_gitlab_project_id": "wingman/cluster-specs",
        "dev_auth_enabled": True,
        "dev_auth_secret": SecretStr(DEV_SECRET),
    }
    base.update(values)
    return Day1Settings(**base)  # ty: ignore[invalid-argument-type]


async def close(adapters: Adapters) -> None:
    for closer in adapters.closers:
        await closer()


async def test_the_fake_backend_is_seeded_with_every_fixture_project() -> None:
    adapters = build_adapters(settings(), FAKE, metrics=metrics(), service_token=lambda: "t")
    try:
        assert isinstance(adapters.gitlab, InstrumentedGitLab)
        for fixture in load_fixture_projects(default_fixture_root()):
            project = await adapters.gitlab.get_project(fixture.path_with_namespace)
            assert project.default_branch == "main"
        assert adapters.hub is None
        assert adapters.identity is None
        assert len(adapters.closers) == 1, "only the day2 client holds a connection"
    finally:
        await close(adapters)


async def test_the_fake_backend_can_be_seeded_from_another_directory(tmp_path: Path) -> None:
    project = tmp_path / "group" / "proj"
    project.mkdir(parents=True)
    (project / "README.md").write_text("# hi\n", encoding="utf-8")
    runtime = FAKE.model_copy(update={"fixtures_dir": tmp_path})
    adapters = build_adapters(settings(), runtime, metrics=metrics(), service_token=lambda: "t")
    try:
        assert (await adapters.gitlab.get_project("group/proj")).path_with_namespace == "group/proj"
    finally:
        await close(adapters)


async def test_the_gitlab_backend_builds_every_real_adapter_without_calling_anything(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GITLAB_URL", "http://gitlab.example.invalid")
    monkeypatch.setenv("GITLAB_TOKEN", "test-token-never-logged-0001")
    tokens = tmp_path / "tokens"
    tokens.write_text("ocp4-prod-mce-site1-a: sa-token\n", encoding="utf-8")
    configured = settings(
        cluster_status_enabled=True,
        mce_tokens_file=tokens,
        mce_api_domain="example.invalid",
        openshift_api_host="api.hub.example.invalid:6443",
        openshift_oauth_client_id="wingman",
        openshift_oauth_client_secret=SecretStr("client-secret"),
        openshift_oauth_redirect_uri="https://wingman.example.invalid/login",
    )
    adapters = build_adapters(configured, REAL, metrics=metrics(), service_token=lambda: "t")
    try:
        assert isinstance(adapters.gitlab, InstrumentedGitLab)
        assert isinstance(adapters.hub, HttpHubApi)
        assert isinstance(adapters.identity, OpenShiftOAuth)
        assert len(adapters.closers) == 4
    finally:
        await close(adapters)


def test_status_enabled_without_a_tokens_file_refuses_to_start(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        build_adapters(
            settings(cluster_status_enabled=True, mce_tokens_file=tmp_path / "absent"),
            FAKE,
            metrics=metrics(),
            service_token=lambda: "t",
        )


def test_the_app_serves_the_legacy_paths_and_no_site_or_mce_creation(app: FastAPI) -> None:
    # FastAPI keeps included routers nested; the OpenAPI document lists every route.
    routes = {
        (path, method.upper()) for path, item in app.openapi()["paths"].items() for method in item
    }
    expected = {
        ("/api/auth/config", "GET"),
        ("/api/auth/callback", "POST"),
        ("/api/auth/dev-login", "POST"),
        ("/api/auth/me", "GET"),
        ("/api/day1/clusters", "GET"),
        ("/api/day1/clusters", "POST"),
        ("/api/day1/clusters/drift-summary", "GET"),
        ("/api/day1/clusters/bulk-status", "POST"),
        ("/api/day1/clusters/preview", "POST"),
        ("/api/day1/clusters/{name}", "GET"),
        ("/api/day1/clusters/{name}", "PATCH"),
        ("/api/day1/clusters/{name}", "DELETE"),
        ("/api/day1/clusters/{name}/status", "GET"),
        ("/api/day1/clusters/{name}/status/stream", "GET"),
        ("/api/day1/clusters/{name}/history", "GET"),
        ("/api/day1/clusters/{name}/current-yaml", "GET"),
        ("/api/day1/clusters/{name}/drift", "GET"),
        ("/api/day1/sites", "GET"),
        ("/api/day1/sites/{site}/mces", "GET"),
        ("/api/day1/mces", "GET"),
        ("/api/day1/mces/{mce}/openshift-versions", "GET"),
        ("/api/day1/mces/{mce}/infraenvs", "GET"),
        ("/api/day1/specs", "GET"),
        ("/api/day1/specs", "POST"),
        ("/api/day1/specs/template", "GET"),
        ("/api/day1/specs/template/schema", "GET"),
        ("/api/day1/specs/{name}", "GET"),
        ("/api/day1/specs/{name}", "PUT"),
        ("/api/day1/specs/{name}", "DELETE"),
        ("/api/day1/specs/{name}/history", "GET"),
        ("/api/day1/specs/{name}/at/{sha}", "GET"),
        ("/api/day1/specs/{name}/clusters", "GET"),
        ("/api/day1/specs/{name}/drift", "GET"),
        ("/api/day1/approvals", "GET"),
        ("/api/day1/approvals/{iid}", "GET"),
        ("/api/day1/approvals/{iid}", "PUT"),
        ("/api/day1/approvals/{iid}/approve", "POST"),
        ("/api/day1/approvals/{iid}/reject", "POST"),
        ("/api/day1/audit/commits", "GET"),
        ("/api/day1/audit/merge-requests", "GET"),
        ("/api/day1/audit/commits/{repo}/{sha}/diff", "GET"),
        ("/api/webhooks/gitlab", "POST"),
    }
    assert expected <= routes
    assert ("/api/day1/sites", "POST") not in routes
    assert ("/api/day1/sites/{site}/mces", "POST") not in routes
    assert not any("sync-yaml" in path for path, _ in routes)


async def test_readiness_asks_gitlab_for_both_projects(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"gitlab": "ok"}}
    assert (await client.get("/metrics")).status_code == 200


async def test_without_the_specs_project_day1_is_not_ready() -> None:
    gitlab = InMemoryGitLab()
    gitlab.create_project("gitops-day1/platform-config", {"README.md": "day1"})
    app = create_app(
        settings=settings(),
        auth=AuthSettings(jwt_secret_key=SecretStr("j" * 40)),
        runtime=FAKE,
        adapters=Adapters(gitlab=gitlab, day2=FakeDay2Addons(), closers=()),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://day1"
    ) as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {"gitlab": "error: NotFoundError"}


async def test_shutting_down_closes_every_adapter() -> None:
    closed: list[str] = []

    async def closer() -> None:
        closed.append("x")

    app = create_app(
        settings=settings(),
        auth=AuthSettings(jwt_secret_key=SecretStr("j" * 40)),
        runtime=FAKE,
        adapters=Adapters(gitlab=InMemoryGitLab(), day2=FakeDay2Addons(), closers=(closer, closer)),
    )
    async with app.router.lifespan_context(app):
        assert closed == []
    assert closed == ["x", "x"]


def test_the_module_builds_app_once_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "WINGMAN_ENVIRONMENT": "development",
        "WINGMAN_GIT_BACKEND": "fake",
        "JWT_SECRET_KEY": "j" * 40,
        "DAY1_GITLAB_PROJECT_ID": "gitops-day1/platform-config",
        "SPECS_GITLAB_PROJECT_ID": "wingman/cluster-specs",
        "DEV_AUTH_ENABLED": "true",
        "DEV_AUTH_SECRET": DEV_SECRET,
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(main, "_app", None)
    built = main.app
    assert isinstance(built, FastAPI)
    assert main.app is built
    with pytest.raises(AttributeError):
        _ = main.application
