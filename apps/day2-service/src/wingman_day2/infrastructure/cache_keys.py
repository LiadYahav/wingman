"""One function per cache key family (ADR-0011).

Reads build their keys here and writes invalidate through the same
functions, so a key and its invalidation cannot drift apart. Everything read
from one team project shares :func:`project_prefix`, which is what a write to
that project clears.
"""

from __future__ import annotations

from wingman_core.domain.git import RepoPath


def teams() -> str:
    """The sigs group's project list."""
    return "day2:teams"


def access(project_id: int) -> str:
    """Wingman's access to a team project; outside the project prefix, as no write changes it."""
    return f"day2:access:{project_id}"


def project_prefix(project_id: int) -> str:
    """Every key of one project: what a write to it invalidates."""
    return f"day2:project:{project_id}:"


def open_merge_requests(project_id: int) -> str:
    """Open Wingman MRs of a project."""
    return f"{project_prefix(project_id)}mrs:open"


def merge_requests(project_id: int, limit: int) -> str:
    """Wingman MRs of a project in any state."""
    return f"{project_prefix(project_id)}mrs:all:{limit}"


def commits(project_id: int, ref: str, path: RepoPath | None, limit: int) -> str:
    """Commits of a project, optionally under ``path``."""
    return f"{project_prefix(project_id)}commits:{ref}:{path or ''}:{limit}"


def day1_project(project: int | str) -> str:
    """The day1 project, by the id or path in the settings."""
    return f"day2:day1-project:{project}"


def day1_index(project_id: int, commit_id: str) -> str:
    """The day1 repo's MCEs, hosted clusters and versions at one commit."""
    return f"day2:day1:{project_id}:{commit_id}"


def chart_project(path: str) -> str:
    """A chart repo looked up by path (or its absence)."""
    return f"day2:chart:project:{path}"


def chart_branches(project_id: int) -> str:
    """A chart repo's branches."""
    return f"day2:chart:{project_id}:branches"


def chart_values(project_id: int, ref: str, path: RepoPath) -> str:
    """A chart's ``values.yaml`` at a revision."""
    return f"day2:chart:{project_id}:values:{ref}:{path}"
