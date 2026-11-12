"""InstrumentedGitLab: any GitLabPort, with every call counted and timed.

A wrapper rather than code inside the adapter, so the fake (local
development, E2E) reports the same metrics as production does.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Sequence

from wingman_core.domain.git import (
    AccessLevel,
    Branch,
    Commit,
    CommitAuthor,
    FileChange,
    FileContent,
    FileDiff,
    Project,
    RepoArchive,
    RepoPath,
    TreeEntry,
)
from wingman_core.domain.merge_request import (
    MergeRequest,
    MergeRequestRef,
    MRState,
    NewMergeRequest,
)
from wingman_core.observability.metrics import (
    Dependency,
    GitLabOperation,
    WingmanMetrics,
    outcome_of,
)
from wingman_core.ports.gitlab import GitLabPort


class InstrumentedGitLab:
    """A GitLabPort that records ``wingman_dependency_*`` for each call to ``inner``."""

    def __init__(
        self,
        inner: GitLabPort,
        metrics: WingmanMetrics,
        *,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        """Wrap ``inner``; ``timer`` is injectable for tests."""
        self._inner = inner
        self._metrics = metrics
        self._timer = timer

    async def _call[T](self, operation: GitLabOperation, call: Awaitable[T]) -> T:
        start = self._timer()
        error: BaseException | None = None
        try:
            return await call
        except BaseException as exc:
            error = exc
            raise
        finally:
            self._metrics.observe_dependency(
                Dependency.GITLAB, operation, outcome_of(error), self._timer() - start
            )

    async def get_project(self, project: int | str) -> Project:
        """See GitLabPort.get_project."""
        return await self._call(GitLabOperation.GET_PROJECT, self._inner.get_project(project))

    async def list_group_projects(self, group: str) -> list[Project]:
        """See GitLabPort.list_group_projects."""
        return await self._call(
            GitLabOperation.LIST_GROUP_PROJECTS, self._inner.list_group_projects(group)
        )

    async def access_level(self, project_id: int) -> AccessLevel:
        """See GitLabPort.access_level."""
        return await self._call(GitLabOperation.ACCESS_LEVEL, self._inner.access_level(project_id))

    async def read_file(self, project_id: int, path: RepoPath, ref: str) -> FileContent:
        """See GitLabPort.read_file."""
        return await self._call(
            GitLabOperation.READ_FILE, self._inner.read_file(project_id, path, ref)
        )

    async def list_tree(
        self, project_id: int, path: RepoPath, ref: str, *, recursive: bool = False
    ) -> list[TreeEntry]:
        """See GitLabPort.list_tree."""
        return await self._call(
            GitLabOperation.LIST_TREE,
            self._inner.list_tree(project_id, path, ref, recursive=recursive),
        )

    async def list_branches(self, project_id: int) -> list[Branch]:
        """See GitLabPort.list_branches."""
        return await self._call(
            GitLabOperation.LIST_BRANCHES, self._inner.list_branches(project_id)
        )

    async def get_branch(self, project_id: int, name: str) -> Branch:
        """See GitLabPort.get_branch."""
        return await self._call(
            GitLabOperation.GET_BRANCH, self._inner.get_branch(project_id, name)
        )

    async def read_archive(self, project_id: int, sha: str, *, max_bytes: int) -> RepoArchive:
        """See GitLabPort.read_archive."""
        return await self._call(
            GitLabOperation.READ_ARCHIVE,
            self._inner.read_archive(project_id, sha, max_bytes=max_bytes),
        )

    async def create_branch(self, project_id: int, name: str, ref: str) -> Branch:
        """See GitLabPort.create_branch."""
        return await self._call(
            GitLabOperation.CREATE_BRANCH, self._inner.create_branch(project_id, name, ref)
        )

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
        """See GitLabPort.commit."""
        return await self._call(
            GitLabOperation.COMMIT,
            self._inner.commit(
                project_id,
                branch=branch,
                message=message,
                changes=changes,
                start_branch=start_branch,
                author=author,
            ),
        )

    async def list_commits(
        self, project_id: int, *, ref: str, path: RepoPath | None = None, limit: int = 50
    ) -> list[Commit]:
        """See GitLabPort.list_commits."""
        return await self._call(
            GitLabOperation.LIST_COMMITS,
            self._inner.list_commits(project_id, ref=ref, path=path, limit=limit),
        )

    async def get_commit(self, project_id: int, sha: str) -> Commit:
        """See GitLabPort.get_commit."""
        return await self._call(GitLabOperation.GET_COMMIT, self._inner.get_commit(project_id, sha))

    async def commit_diff(self, project_id: int, sha: str) -> list[FileDiff]:
        """See GitLabPort.commit_diff."""
        return await self._call(
            GitLabOperation.COMMIT_DIFF, self._inner.commit_diff(project_id, sha)
        )

    async def create_merge_request(self, project_id: int, request: NewMergeRequest) -> MergeRequest:
        """See GitLabPort.create_merge_request."""
        return await self._call(
            GitLabOperation.CREATE_MERGE_REQUEST,
            self._inner.create_merge_request(project_id, request),
        )

    async def get_merge_request(self, ref: MergeRequestRef) -> MergeRequest:
        """See GitLabPort.get_merge_request."""
        return await self._call(
            GitLabOperation.GET_MERGE_REQUEST, self._inner.get_merge_request(ref)
        )

    async def list_merge_requests(
        self,
        project_id: int,
        *,
        state: MRState | None = MRState.OPENED,
        labels: Sequence[str] = (),
        limit: int = 100,
    ) -> list[MergeRequest]:
        """See GitLabPort.list_merge_requests."""
        return await self._call(
            GitLabOperation.LIST_MERGE_REQUESTS,
            self._inner.list_merge_requests(project_id, state=state, labels=labels, limit=limit),
        )

    async def merge_request_diff(self, ref: MergeRequestRef) -> list[FileDiff]:
        """See GitLabPort.merge_request_diff."""
        return await self._call(
            GitLabOperation.MERGE_REQUEST_DIFF, self._inner.merge_request_diff(ref)
        )

    async def approve_merge_request(self, ref: MergeRequestRef) -> None:
        """See GitLabPort.approve_merge_request."""
        await self._call(
            GitLabOperation.APPROVE_MERGE_REQUEST, self._inner.approve_merge_request(ref)
        )

    async def merge_merge_request(
        self, ref: MergeRequestRef, *, sha: str | None = None
    ) -> MergeRequest:
        """See GitLabPort.merge_merge_request."""
        return await self._call(
            GitLabOperation.MERGE_MERGE_REQUEST, self._inner.merge_merge_request(ref, sha=sha)
        )

    async def close_merge_request(self, ref: MergeRequestRef) -> MergeRequest:
        """See GitLabPort.close_merge_request."""
        return await self._call(
            GitLabOperation.CLOSE_MERGE_REQUEST, self._inner.close_merge_request(ref)
        )

    async def comment_on_merge_request(self, ref: MergeRequestRef, body: str) -> None:
        """See GitLabPort.comment_on_merge_request."""
        await self._call(
            GitLabOperation.COMMENT_ON_MERGE_REQUEST,
            self._inner.comment_on_merge_request(ref, body),
        )
