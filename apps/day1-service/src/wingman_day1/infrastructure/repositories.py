"""CachedRepository: the cached read side of one GitLab project (``RepoReads``).

Reads at the default branch are cached for a few seconds (ADR-0011);
reads at any other ref (an MR's branch, a commit) are not, because CI and
the allocate-segment workflow move MR branches behind Wingman's back. A
failed read is never cached. Concurrent misses share one GitLab call.
"""

from __future__ import annotations

from collections.abc import Sequence

from wingman_core.domain.git import Commit, FileContent, FileDiff, Project, RepoPath, TreeEntry
from wingman_core.domain.merge_request import MergeRequest, MRState
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.ports.gitlab import GitLabPort
from wingman_day1.infrastructure import cache_keys as keys


class CachedRepository:
    """``RepoReads`` for one project, over any ``GitLabPort`` and one shared ``TtlCache``."""

    def __init__(
        self,
        gitlab: GitLabPort,
        cache: TtlCache,
        *,
        key: str,
        project: int | str,
        ttl: float,
    ) -> None:
        """``key`` names the repository in cache keys (``day1``, ``specs``)."""
        self._gitlab = gitlab
        self._cache = cache
        self._key = key
        self._project = project
        self._ttl = ttl

    @property
    def key(self) -> str:
        """The repository's short key."""
        return self._key

    async def project(self) -> Project:
        """See RepoReads.project."""
        return await self._cache.get_or_fetch(
            keys.project(self._key), lambda: self._gitlab.get_project(self._project), ttl=self._ttl
        )

    async def tree(self, path: RepoPath, *, recursive: bool = False) -> list[TreeEntry]:
        """See RepoReads.tree."""
        project = await self.project()
        return await self._cache.get_or_fetch(
            keys.tree(self._key, path, recursive=recursive),
            lambda: self._gitlab.list_tree(
                project.id, path, project.default_branch, recursive=recursive
            ),
            ttl=self._ttl,
        )

    async def read(self, path: RepoPath, *, ref: str | None = None) -> FileContent:
        """See RepoReads.read."""
        project = await self.project()
        if ref is not None and ref != project.default_branch:
            return await self._gitlab.read_file(project.id, path, ref)
        return await self._cache.get_or_fetch(
            keys.file(self._key, path),
            lambda: self._gitlab.read_file(project.id, path, project.default_branch),
            ttl=self._ttl,
        )

    async def history(self, path: RepoPath, *, limit: int = 50) -> list[Commit]:
        """See RepoReads.history."""
        project = await self.project()
        return await self._cache.get_or_fetch(
            keys.history(self._key, path, limit=limit),
            lambda: self._gitlab.list_commits(
                project.id, ref=project.default_branch, path=path, limit=limit
            ),
            ttl=self._ttl,
        )

    async def commits(self, *, limit: int) -> list[Commit]:
        """See RepoReads.commits."""
        project = await self.project()
        return await self._cache.get_or_fetch(
            keys.commits(self._key, limit=limit),
            lambda: self._gitlab.list_commits(project.id, ref=project.default_branch, limit=limit),
            ttl=self._ttl,
        )

    async def commit(self, sha: str) -> Commit:
        """See RepoReads.commit."""
        project = await self.project()
        return await self._cache.get_or_fetch(
            keys.commit(self._key, sha),
            lambda: self._gitlab.get_commit(project.id, sha),
            ttl=self._ttl,
        )

    async def commit_diff(self, sha: str) -> list[FileDiff]:
        """See RepoReads.commit_diff."""
        project = await self.project()
        return await self._cache.get_or_fetch(
            keys.commit_diff(self._key, sha),
            lambda: self._gitlab.commit_diff(project.id, sha),
            ttl=self._ttl,
        )

    async def merge_requests(
        self, *, state: MRState | None, labels: Sequence[str] = (), limit: int = 100
    ) -> list[MergeRequest]:
        """See RepoReads.merge_requests."""
        project = await self.project()
        return await self._cache.get_or_fetch(
            keys.merge_requests(self._key, state=state, labels=labels, limit=limit),
            lambda: self._gitlab.list_merge_requests(
                project.id, state=state, labels=labels, limit=limit
            ),
            ttl=self._ttl,
        )

    def forget_files(self) -> None:
        """See RepoReads.forget_files."""
        self._cache.invalidate_prefix(keys.files_prefix(self._key))

    def forget_merge_requests(self) -> None:
        """See RepoReads.forget_merge_requests."""
        self._cache.invalidate_prefix(keys.merge_requests_prefix(self._key))
