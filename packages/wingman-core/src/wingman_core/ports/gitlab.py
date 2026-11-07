"""The GitLab port: everything Wingman needs from its Git hosting.

Two implementations exist: ``GitLabHttpAdapter`` (the real REST API) and
``InMemoryGitLab`` (tests and local development). Both are held to the same
behaviour by one contract suite (``wingman_core.testing.gitlab_contract``,
ADR-0005). Every method raises only ``wingman_core.domain.errors`` types.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from wingman_core.domain.git import (
    Branch,
    Commit,
    CommitAuthor,
    FileChange,
    FileContent,
    FileDiff,
    Project,
    RepoPath,
    TreeEntry,
)
from wingman_core.domain.merge_request import (
    MergeRequest,
    MergeRequestRef,
    MRState,
    NewMergeRequest,
)


class GitLabPort(Protocol):
    """Reads and writes against GitLab projects. All methods are async."""

    async def get_project(self, project: int | str) -> Project:
        """A project by numeric id or by ``group/sub/name`` path."""
        ...

    async def list_group_projects(self, group: str) -> list[Project]:
        """Every project directly in a group (not in its subgroups), sorted by path."""
        ...

    async def read_file(self, project_id: int, path: RepoPath, ref: str) -> FileContent:
        """A file's text at a ref. Raises ``NotFoundError`` if it is absent."""
        ...

    async def list_tree(
        self, project_id: int, path: RepoPath, ref: str, *, recursive: bool = False
    ) -> list[TreeEntry]:
        """The entries under a directory, sorted by path.

        Raises ``NotFoundError`` if the directory does not exist at ``ref``.
        """
        ...

    async def list_branches(self, project_id: int) -> list[Branch]:
        """Every branch of a project, sorted by name."""
        ...

    async def create_branch(self, project_id: int, name: str, ref: str) -> Branch:
        """Create a branch at ``ref``. Raises ``AlreadyExistsError`` if it exists."""
        ...

    async def commit(
        self,
        project_id: int,
        *,
        branch: str,
        message: str,
        changes: Sequence[FileChange],
        start_branch: str | None = None,
        author: CommitAuthor | None = None,
    ) -> Commit:
        """Commit file changes atomically: all of them apply or none do.

        With ``start_branch``, ``branch`` is created from it first. With
        ``author``, the commit is authored by that person; the token's account
        stays the committer. Raises
        ``AlreadyExistsError`` (create of an existing file), ``NotFoundError``
        (update or delete of a missing file) or ``RevisionConflictError`` (a
        stale ``last_commit_id``). Never retried (ADR-0006).
        """
        ...

    async def list_commits(
        self, project_id: int, *, ref: str, path: RepoPath | None = None, limit: int = 50
    ) -> list[Commit]:
        """Up to ``limit`` commits reachable from ``ref``, newest first.

        With ``path``, only commits that changed something at or below it.
        """
        ...

    async def get_commit(self, project_id: int, sha: str) -> Commit:
        """One commit. Raises ``NotFoundError`` if it does not exist."""
        ...

    async def commit_diff(self, project_id: int, sha: str) -> list[FileDiff]:
        """What a commit changed, against its first parent."""
        ...

    async def create_merge_request(self, project_id: int, request: NewMergeRequest) -> MergeRequest:
        """Open a merge request. Raises ``AlreadyExistsError`` if one is open for the branch."""
        ...

    async def get_merge_request(self, ref: MergeRequestRef) -> MergeRequest:
        """One merge request. Raises ``NotFoundError`` if it does not exist."""
        ...

    async def list_merge_requests(
        self,
        project_id: int,
        *,
        state: MRState | None = MRState.OPENED,
        labels: Sequence[str] = (),
        limit: int = 100,
    ) -> list[MergeRequest]:
        """Merge requests, newest first, filtered by state (``None`` = any) and all ``labels``."""
        ...

    async def merge_request_diff(self, ref: MergeRequestRef) -> list[FileDiff]:
        """What a merge request changes, against its target branch."""
        ...

    async def approve_merge_request(self, ref: MergeRequestRef) -> None:
        """Approve as the configured account."""
        ...

    async def merge_merge_request(
        self, ref: MergeRequestRef, *, sha: str | None = None
    ) -> MergeRequest:
        """Merge into the target branch.

        With ``sha``, the merge only happens if the source branch is still at
        that commit; otherwise ``RevisionConflictError``. Raises
        ``NotMergeableError`` if the MR cannot be merged. A source branch the
        MR asked to remove may still exist right after the merge: GitLab
        deletes it in a background job.
        """
        ...

    async def close_merge_request(self, ref: MergeRequestRef) -> MergeRequest:
        """Close without merging."""
        ...
