"""Settings fail closed (ADR-0009)."""

from __future__ import annotations

import pytest
from pydantic import AnyHttpUrl, SecretStr, ValidationError

from wingman_core.settings import Environment, GitBackend, GitLabSettings, RuntimeSettings


def test_fake_backend_is_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="refused"):
        RuntimeSettings(environment=Environment.PRODUCTION, git_backend=GitBackend.FAKE)
    assert RuntimeSettings(environment=Environment.DEVELOPMENT, git_backend=GitBackend.FAKE)


def test_production_and_real_gitlab_are_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WINGMAN_ENVIRONMENT", raising=False)
    monkeypatch.delenv("WINGMAN_GIT_BACKEND", raising=False)
    settings = RuntimeSettings()
    assert (settings.environment, settings.git_backend) == (
        Environment.PRODUCTION,
        GitBackend.GITLAB,
    )


def test_empty_gitlab_token_is_refused() -> None:
    with pytest.raises(ValidationError, match="GITLAB_TOKEN is empty"):
        GitLabSettings(url=AnyHttpUrl("http://gl"), token=SecretStr("  "))


def test_gitlab_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.internal")
    monkeypatch.setenv("GITLAB_TOKEN", "t0k3n")
    settings = GitLabSettings()  # type: ignore[call-arg]
    assert settings.token.get_secret_value() == "t0k3n"
    assert "t0k3n" not in repr(settings)
