"""CachedRepository: the cached read side of one GitLab project (``RepoReads``).

Files and trees at the default branch come from ``RepoSnapshots`` (ADR-0035):
one head check per TTL, one archive per commit. History, commits and merge
requests are cached for a few seconds (ADR-0011). Reads at any other ref (an
MR's branch, a commit) are not cached, because CI and the allocate-segment
workflow move MR branches behind Wingman's back. A failed read is never
cached. Concurrent misses share one GitLab call.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import (
    Commit,
    FileContent,
    FileDiff,
    Project,
    RepoPath,
    TreeEntry,
    tree_of,
)
from wingman_core.domain.merge_request import MergeRequest, MRState
from wingman_core.infrastructure.cache import TtlCache, stale_for
from wingman_core.infrastructure.snapshots import RepoFiles, RepoSnapshots
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
        snapshots: RepoSnapshots | None = None,
    ) -> None:
        """``key`` names the repository in cache keys (``day1``, ``specs``).

        ``snapshots`` is shared by the repositories of one service, so they
        share one memory budget; by default the repository has its own.
        """
        self._gitlab = gitlab
        self._cache = cache
        self._key = key
        self._project = project
        self._ttl = ttl
        self._snapshots = snapshots or RepoSnapshots(gitlab, cache, ttl=ttl)
        self._project_id: int | None = None
        self._last_changes: tuple[str, dict[str, asyncio.Task[list[Commit]]]] = ("", {})

    @property
    def key(self) -> str:
        """The repository's short key."""
        return self._key

    async def project(self) -> Project:
        """See RepoReads.project."""
        project = await self._cache.get_or_fetch(
            keys.project(self._key),
            lambda: self._gitlab.get_project(self._project),
            ttl=self._ttl,
            stale=stale_for(self._ttl),
        )
        self._project_id = project.id
        return project

    async def _files(self) -> tuple[Project, RepoFiles | None]:
        project = await self.project()
        return project, await self._snapshots.files(project.id, project.default_branch)

    async def tree(self, path: RepoPath, *, recursive: bool = False) -> list[TreeEntry]:
        """See RepoReads.tree (an empty repository has an empty root)."""
        project, files = await self._files()
        entries = tree_of(files.paths if files else frozenset(), path, recursive=recursive)
        if entries is not None:
            return entries
        if path.is_root:
            return []
        raise NotFoundError(f"tree {path} not found at {project.default_branch}")

    async def read(self, path: RepoPath, *, ref: str | None = None) -> FileContent:
        """See RepoReads.read; at the default branch, ``last_commit_id`` is the commit read at."""
        project = await self.project()
        if ref is not None and ref != project.default_branch:
            return await self._gitlab.read_file(project.id, path, ref)
        project, files = await self._files()
        content = await files.read(path) if files else None
        if files is None or content is None:
            raise NotFoundError(f"{path} not found at {project.default_branch}")
        return FileContent(
            path=path, ref=project.default_branch, content=content, last_commit_id=files.commit_id
        )

    async def last_change(self, path: RepoPath) -> Commit | None:
        """See RepoReads.last_change: one history lookup per file, kept while the head stays."""
        project, files = await self._files()
        if files is None:
            return None
        commit_id, known = self._last_changes
        if commit_id != files.commit_id:
            commit_id, known = files.commit_id, {}
            self._last_changes = (commit_id, known)
        task = known.get(str(path))
        if task is None:
            task = asyncio.ensure_future(
                self._gitlab.list_commits(project.id, ref=commit_id, path=path, limit=1)
            )
            known[str(path)] = task
        try:
            found = await asyncio.shield(task)
        except BaseException:
            if known.get(str(path)) is task and task.done():
                del known[str(path)]  # a failed lookup is not kept
            raise
        return found[0] if found else None

    async def changed_since(self, path: RepoPath, commit_id: str) -> bool:
        """See RepoReads.changed_since: two history lookups, never cached."""
        project = await self.project()
        try:
            then = await self._gitlab.list_commits(project.id, ref=commit_id, path=path, limit=1)
        except NotFoundError:
            return True
        now = await self._gitlab.list_commits(
            project.id, ref=project.default_branch, path=path, limit=1
        )
        return not then or not now or then[0].id != now[0].id

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
        if self._project_id is not None:
            self._snapshots.forget(self._project_id)

    def forget_merge_requests(self) -> None:
        """See RepoReads.forget_merge_requests."""
        self._cache.invalidate_prefix(keys.merge_requests_prefix(self._key))
