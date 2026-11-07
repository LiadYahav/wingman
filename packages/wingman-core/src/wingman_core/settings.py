"""Settings shared by every Wingman service.

Settings fail closed (ADR-0009): a configuration that would run insecurely,
or run the fake Git backend in production, refuses to start instead of
starting degraded.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Where a service runs."""

    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TEST = "test"


class GitBackend(StrEnum):
    """Which GitLabPort implementation a service uses."""

    GITLAB = "gitlab"
    FAKE = "fake"


class GitLabSettings(BaseSettings):
    """How to reach GitLab. Environment variables ``GITLAB_*``."""

    model_config = SettingsConfigDict(env_prefix="GITLAB_", extra="ignore")

    url: AnyHttpUrl
    token: SecretStr
    verify_tls: bool = True
    connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    read_timeout_seconds: float = Field(default=20.0, gt=0, le=300)

    @model_validator(mode="after")
    def _token_present(self) -> Self:
        """An empty token would make every call fail with 401; refuse it up front."""
        if not self.token.get_secret_value().strip():
            raise ValueError("GITLAB_TOKEN is empty")
        return self


class RuntimeSettings(BaseSettings):
    """Where and how a service runs. Environment variables ``WINGMAN_*``."""

    model_config = SettingsConfigDict(env_prefix="WINGMAN_", extra="ignore")

    environment: Environment = Environment.PRODUCTION
    git_backend: GitBackend = GitBackend.GITLAB

    @model_validator(mode="after")
    def _no_fake_in_production(self) -> Self:
        """The fake keeps everything in memory; in production that silently loses every change."""
        if self.environment is Environment.PRODUCTION and self.git_backend is GitBackend.FAKE:
            raise ValueError(
                "WINGMAN_GIT_BACKEND=fake is refused when WINGMAN_ENVIRONMENT=production"
            )
        return self
