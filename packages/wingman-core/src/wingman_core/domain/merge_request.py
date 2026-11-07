"""Merge requests.

A merge request is identified by its project and its per-project number
together (ADR-0007). The number alone is ambiguous: every team's day2 repo has
its own ``!5``, and acting on "MR 5" without the project approved or merged the
wrong team's change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MRState(StrEnum):
    """A merge request's lifecycle state; the values are GitLab's."""

    OPENED = "opened"
    CLOSED = "closed"
    MERGED = "merged"
    LOCKED = "locked"


@dataclass(frozen=True, slots=True, order=True)
class MergeRequestRef:
    """The identity of a merge request: ``(project_id, iid)``."""

    project_id: int
    iid: int

    def __str__(self) -> str:
        """``<project>!<iid>``, GitLab's own cross-project reference style."""
        return f"{self.project_id}!{self.iid}"


@dataclass(frozen=True, slots=True)
class MergeRequest:
    """A merge request as the backend reports it."""

    ref: MergeRequestRef
    title: str
    description: str
    state: MRState
    source_branch: str
    target_branch: str
    author_username: str
    labels: tuple[str, ...]
    web_url: str
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None
    sha: str
    has_conflicts: bool


@dataclass(frozen=True, slots=True)
class NewMergeRequest:
    """What it takes to open a merge request."""

    source_branch: str
    target_branch: str
    title: str
    description: str = ""
    labels: tuple[str, ...] = ()
    remove_source_branch: bool = True
