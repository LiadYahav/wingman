"""day2's settings: the core ones (GitLab, auth, runtime) plus where the repos are (ADR-0009).

- ``DAY2_SIGS_GROUP_PATH`` (required): the sigs group; every project directly in it is a team.
- ``DAY1_GITLAB_PROJECT_ID`` (required): the day1 repo, an id or ``group/name``
  (``gitops-day1/platform-config``).
- ``DAY2_GITOPS_BRANCH``: the branch the platform reads and MRs target (``main``,
  as every generator in the platform charts says).
- ``DAY2_CACHE_TTL_SECONDS``: how long a GitLab read is kept (ADR-0011; at most 60).
- ``WINGMAN_FIXTURES_DIR``: with ``WINGMAN_GIT_BACKEND=fake``, the tree to seed
  the in-memory GitLab from (default ``dev/gitlab-fixtures``).
- ``WINGMAN_VERSION``, ``WINGMAN_COMMIT``: the build ``wingman_build_info`` reports; the
  image sets both, with the same names as day1, so the version-skew alert compares like
  with like.

``GITLAB_URL`` and ``GITLAB_TOKEN`` are required unless the backend is the fake.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from wingman_core.settings import AuthSettings, GitBackend, GitLabSettings, RuntimeSettings
from wingman_day2 import __version__

FAKE_GITLAB_URL = "http://gitlab.fake"


class Day2Settings(BaseSettings):
    """The day2-specific variables (see the module docstring)."""

    model_config = SettingsConfigDict(extra="ignore")

    day2_sigs_group_path: str = Field(min_length=1)
    day1_gitlab_project_id: str = Field(min_length=1)
    day2_gitops_branch: str = Field(default="main", min_length=1)
    day2_cache_ttl_seconds: float = Field(default=15.0, gt=0, le=60)
    wingman_fixtures_dir: Path | None = None
    wingman_version: str = __version__
    wingman_commit: str = "unknown"

    @property
    def day1_project(self) -> int | str:
        """The day1 project as GitLabPort.get_project takes it."""
        value = self.day1_gitlab_project_id.strip()
        return int(value) if value.isdigit() else value


@dataclass(frozen=True, slots=True)
class Config:
    """Everything day2 reads from the environment, validated."""

    runtime: RuntimeSettings
    auth: AuthSettings
    day2: Day2Settings
    gitlab: GitLabSettings | None

    @property
    def gitlab_url(self) -> str:
        """The GitLab's URL (the fake's, for the fake backend)."""
        return str(self.gitlab.url).rstrip("/") if self.gitlab else FAKE_GITLAB_URL


def load_config() -> Config:
    """Read and validate the environment; raises if the configuration is unsafe or incomplete."""
    runtime = RuntimeSettings()
    gitlab = None if runtime.git_backend is GitBackend.FAKE else GitLabSettings()
    return Config(runtime=runtime, auth=AuthSettings(), day2=Day2Settings(), gitlab=gitlab)
