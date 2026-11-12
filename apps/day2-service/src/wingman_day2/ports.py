"""What the day2 use cases need from the outside world (ADR-0001).

Reads go through these repositories, which cache (ADR-0011); writes and merge
requests go through ``wingman_core.ports.gitlab.GitLabPort`` directly, and
every write calls :meth:`SigsRepository.invalidate` for the project it changed.
"""

from __future__ import annotations

from typing import Protocol

from wingman_core.domain.git import AccessLevel, Commit, FileContent, Project, RepoPath
from wingman_core.domain.merge_request import MergeRequest
from wingman_day2.domain.day1 import Day1Index
from wingman_day2.domain.teams import Team
from wingman_day2.domain.tree import RepoTree


class SigsRepository(Protocol):
    """The team repos: every project directly in the sigs group, read at the GitOps branch."""

    @property
    def group(self) -> str:
        """The sigs group's path."""
        ...

    @property
    def branch(self) -> str:
        """The branch the platform deploys from; MRs target it."""
        ...

    async def teams(self) -> list[Team]:
        """Every team, sorted by name."""
        ...

    async def access(self, team: Team) -> AccessLevel:
        """Wingman's account's access to the team's project (ADR-0043).

        ``AccessLevel.NONE`` for a project the account cannot see; a GitLab
        failure raises (``AccessService`` makes it "access unknown").
        """
        ...

    async def tree(self, team: Team) -> RepoTree:
        """The team repo's files."""
        ...

    async def read(self, team: Team, path: RepoPath) -> FileContent | None:
        """A file, or ``None`` when it does not exist."""
        ...

    async def open_merge_requests(self, team: Team) -> list[MergeRequest]:
        """Open Wingman MRs (label ``wingman``) in the team's project, newest first."""
        ...

    async def merge_requests(self, team: Team, *, limit: int) -> list[MergeRequest]:
        """Wingman MRs in any state, newest first."""
        ...

    async def commits(self, team: Team, *, path: RepoPath | None, limit: int) -> list[Commit]:
        """Commits on the branch, newest first, optionally only those touching ``path``."""
        ...

    def invalidate(self, team: Team) -> None:
        """Forget everything cached for the team's project (called by every write to it)."""
        ...


class Day1Repository(Protocol):
    """The day1 repo, read-only for day2."""

    async def index(self) -> Day1Index:
        """Every MCE and hosted cluster day1 knows, with their version files."""
        ...


class ChartRepository(Protocol):
    """Chart repos: one GitLab project per chart; each branch is a frozen release."""

    def on_this_gitlab(self, repo_url: str) -> bool:
        """Whether ``repo_url`` points at this GitLab (scheme, host and sub-path)."""
        ...

    async def resolve(self, repo_url: str) -> Project | None:
        """The project a ``repourl`` names, or ``None`` if it is not on this GitLab."""
        ...

    async def branches(self, project: Project) -> list[str]:
        """Branch names of the chart repo."""
        ...

    async def values(self, project: Project, revision: str, path: RepoPath) -> FileContent | None:
        """``<path>/values.yaml`` at ``revision`` (``HEAD``: default branch), or ``None``."""
        ...
