"""The day2 repositories: GitLabPort reads, cached per replica for seconds (ADR-0011).

A missing file is a normal answer (``None``) and is cached like any other;
every other GitLab error propagates, so a page never shows "nothing here"
when the truth is "GitLab failed" (ADR-0004).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import Commit, EntryKind, FileContent, Project, RepoPath
from wingman_core.domain.merge_request import MergeRequest, MRState
from wingman_core.domain.mr_conventions import WINGMAN_LABEL
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.ports.gitlab import GitLabPort
from wingman_day2.domain.day1 import Day1Index, build_day1_index, day1_version_files
from wingman_day2.domain.deploy_config import DEFAULT_REVISION
from wingman_day2.domain.teams import Team
from wingman_day2.domain.tree import RepoTree
from wingman_day2.infrastructure import cache_keys

_READ_CONCURRENCY = 16


async def _tree(gitlab: GitLabPort, project_id: int, ref: str) -> RepoTree:
    try:
        entries = await gitlab.list_tree(project_id, RepoPath.root(), ref, recursive=True)
    except NotFoundError:
        return RepoTree(frozenset())  # an empty repository has no tree yet
    return RepoTree(frozenset(str(e.path) for e in entries if e.kind is EntryKind.FILE))


async def _read_or_none(
    gitlab: GitLabPort, project_id: int, path: RepoPath, ref: str
) -> FileContent | None:
    try:
        return await gitlab.read_file(project_id, path, ref)
    except NotFoundError:
        return None


class GitLabSigsRepository:
    """The team repos of one sigs group."""

    def __init__(
        self, gitlab: GitLabPort, cache: TtlCache, *, group: str, branch: str, ttl: float
    ) -> None:
        """Read ``group``'s projects at ``branch``; keep each read for ``ttl`` seconds."""
        self._gitlab = gitlab
        self._cache = cache
        self._group = group
        self._branch = branch
        self._ttl = ttl

    @property
    def group(self) -> str:
        """See SigsRepository.group."""
        return self._group

    @property
    def branch(self) -> str:
        """See SigsRepository.branch."""
        return self._branch

    def _cached[T](self, key: str, fetch: Callable[[], Awaitable[T]]) -> Awaitable[T]:
        return self._cache.get_or_fetch(key, fetch, ttl=self._ttl)

    async def teams(self) -> list[Team]:
        """See SigsRepository.teams."""

        async def fetch() -> list[Team]:
            projects = await self._gitlab.list_group_projects(self._group)
            return sorted((Team.of(p) for p in projects), key=lambda t: t.name)

        return await self._cached(cache_keys.teams(), fetch)

    async def tree(self, team: Team) -> RepoTree:
        """See SigsRepository.tree."""
        pid = team.project.id
        return await self._cached(
            cache_keys.tree(pid, self._branch), lambda: _tree(self._gitlab, pid, self._branch)
        )

    async def read(self, team: Team, path: RepoPath) -> FileContent | None:
        """See SigsRepository.read."""
        pid = team.project.id
        return await self._cached(
            cache_keys.file(pid, self._branch, path),
            lambda: _read_or_none(self._gitlab, pid, path, self._branch),
        )

    async def open_merge_requests(self, team: Team) -> list[MergeRequest]:
        """See SigsRepository.open_merge_requests."""
        pid = team.project.id
        return await self._cached(
            cache_keys.open_merge_requests(pid),
            lambda: self._gitlab.list_merge_requests(
                pid, state=MRState.OPENED, labels=(WINGMAN_LABEL,)
            ),
        )

    async def merge_requests(self, team: Team, *, limit: int) -> list[MergeRequest]:
        """See SigsRepository.merge_requests."""
        pid = team.project.id
        return await self._cached(
            cache_keys.merge_requests(pid, limit),
            lambda: self._gitlab.list_merge_requests(
                pid, state=None, labels=(WINGMAN_LABEL,), limit=limit
            ),
        )

    async def commits(self, team: Team, *, path: RepoPath | None, limit: int) -> list[Commit]:
        """See SigsRepository.commits."""
        pid = team.project.id

        async def fetch() -> list[Commit]:
            try:
                return await self._gitlab.list_commits(
                    pid, ref=self._branch, path=path, limit=limit
                )
            except NotFoundError:
                return []  # an empty repository has no branch yet

        return await self._cached(cache_keys.commits(pid, self._branch, path, limit), fetch)

    def invalidate(self, team: Team) -> None:
        """See SigsRepository.invalidate."""
        self._cache.invalidate_prefix(cache_keys.project_prefix(team.project.id))


class GitLabDay1Repository:
    """The day1 repo, read at the branch the platform reads (``main``)."""

    def __init__(
        self, gitlab: GitLabPort, cache: TtlCache, *, project: int | str, branch: str, ttl: float
    ) -> None:
        """``project`` is an id or ``group/name`` path."""
        self._gitlab = gitlab
        self._cache = cache
        self._project = project
        self._branch = branch
        self._ttl = ttl

    async def index(self) -> Day1Index:
        """See Day1Repository.index."""

        async def fetch() -> Day1Index:
            project = await self._gitlab.get_project(self._project)
            tree = await _tree(self._gitlab, project.id, self._branch)
            limit = asyncio.Semaphore(_READ_CONCURRENCY)

            async def read(path: RepoPath) -> tuple[str, FileContent | None]:
                async with limit:
                    return str(path), await _read_or_none(
                        self._gitlab, project.id, path, self._branch
                    )

            files = await asyncio.gather(*(read(p) for p in day1_version_files(tree)))
            return build_day1_index(tree, {p: f.content for p, f in files if f is not None})

        return await self._cache.get_or_fetch(
            cache_keys.day1_index(self._project, self._branch), fetch, ttl=self._ttl
        )


class GitLabChartRepository:
    """Chart repos on the same GitLab, found from a deploy config's ``repourl``."""

    def __init__(self, gitlab: GitLabPort, cache: TtlCache, *, base_url: str, ttl: float) -> None:
        """``base_url`` is the GitLab's own URL; a ``repourl`` elsewhere is not resolved."""
        self._gitlab = gitlab
        self._cache = cache
        base = urlsplit(base_url.rstrip("/"))
        self._host = base.netloc.lower()
        self._prefix = base.path.rstrip("/")
        self._ttl = ttl

    def project_path(self, repo_url: str) -> str | None:
        """``group/.../name`` for a ``repourl`` on this GitLab, else ``None``."""
        url = urlsplit(repo_url.strip())
        if url.scheme not in ("http", "https") or url.netloc.lower() != self._host:
            return None
        path = url.path
        if self._prefix:
            if not path.startswith(f"{self._prefix}/"):
                return None
            path = path[len(self._prefix) :]
        path = path.strip("/").removesuffix(".git")
        return path or None

    async def resolve(self, repo_url: str) -> Project | None:
        """See ChartRepository.resolve."""
        path = self.project_path(repo_url)
        if path is None:
            return None

        async def fetch() -> Project | None:
            try:
                return await self._gitlab.get_project(path)
            except NotFoundError:
                return None

        return await self._cache.get_or_fetch(cache_keys.chart_project(path), fetch, ttl=self._ttl)

    async def branches(self, project: Project) -> list[str]:
        """See ChartRepository.branches."""

        async def fetch() -> list[str]:
            return [b.name for b in await self._gitlab.list_branches(project.id)]

        return await self._cache.get_or_fetch(
            cache_keys.chart_branches(project.id), fetch, ttl=self._ttl
        )

    async def values(self, project: Project, revision: str, path: RepoPath) -> FileContent | None:
        """See ChartRepository.values."""
        ref = project.default_branch if revision == DEFAULT_REVISION else revision
        file = path.child("values.yaml")
        return await self._cache.get_or_fetch(
            cache_keys.chart_values(project.id, ref, file),
            lambda: _read_or_none(self._gitlab, project.id, file, ref),
            ttl=self._ttl,
        )
