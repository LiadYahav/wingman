"""Settings fail closed (ADR-0009)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import AnyHttpUrl, SecretStr, ValidationError

from wingman_core.settings import (
    Environment,
    GitBackend,
    GitLabSettings,
    RuntimeSettings,
    project_ref,
)


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


def test_the_build_and_the_fixtures_come_from_the_wingman_variables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("WINGMAN_VERSION", "1.4.0")
    monkeypatch.setenv("WINGMAN_COMMIT", "abc1234")
    monkeypatch.setenv("WINGMAN_FIXTURES_DIR", str(tmp_path))
    settings = RuntimeSettings()
    assert (settings.version, settings.commit, settings.fixtures_dir) == (
        "1.4.0",
        "abc1234",
        tmp_path,
    )


def test_a_local_run_says_it_is_no_release(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("WINGMAN_VERSION", "WINGMAN_COMMIT", "WINGMAN_FIXTURES_DIR"):
        monkeypatch.delenv(name, raising=False)
    settings = RuntimeSettings()
    assert (settings.version, settings.commit, settings.fixtures_dir) == ("dev", "unknown", None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("42", 42),
        (" 42 ", 42),
        ("gitops-day1/platform-config", "gitops-day1/platform-config"),
        (" /a/b/ ", "a/b"),
    ],
)
def test_a_project_setting_is_an_id_or_a_path(value: str, expected: int | str) -> None:
    assert project_ref(value) == expected


def test_empty_gitlab_token_is_refused() -> None:
    with pytest.raises(ValidationError, match="GITLAB_TOKEN is empty"):
        GitLabSettings(url=AnyHttpUrl("http://gl"), token=SecretStr("  "))


def test_gitlab_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_URL", "https://gitlab.internal")
    monkeypatch.setenv("GITLAB_TOKEN", "t0k3n")
    settings = GitLabSettings()  # type: ignore[call-arg]
    assert settings.token.get_secret_value() == "t0k3n"
    assert "t0k3n" not in repr(settings)
