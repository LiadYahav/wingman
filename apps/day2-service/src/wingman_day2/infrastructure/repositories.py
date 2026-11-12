"""The day2 repositories: GitLabPort reads, cached per replica (ADR-0011, ADR-0035).

The team repos and the day1 repo are read through ``RepoSnapshots``: one
head check per TTL, one archive per commit. Merge requests, history and chart
repos are read call by call and kept for the TTL.

A missing file is a normal answer (``None``); every other GitLab error
propagates, so a page never shows "nothing here" when the truth is "GitLab
failed" (ADR-0004).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import AccessLevel, Commit, FileContent, Project, RepoPath
from wingman_core.domain.merge_request import MergeRequest, MRState
from wingman_core.domain.mr_conventions import WINGMAN_LABEL
from wingman_core.infrastructure.cache import TtlCache, stale_for
from wingman_core.infrastructure.snapshots import RepoFiles, RepoSnapshots
from wingman_core.ports.gitlab import GitLabPort
from wingman_day2.domain.day1 import Day1Index, build_day1_index, day1_version_files
from wingman_day2.domain.deploy_config import DEFAULT_REVISION
from wingman_day2.domain.teams import Team
from wingman_day2.domain.tree import RepoTree
from wingman_day2.infrastructure import cache_keys


async def _read_or_none(
    gitlab: GitLabPort, project_id: int, path: RepoPath, ref: str
) -> FileContent | None:
    try:
        return await gitlab.read_file(project_id, path, ref)
    except NotFoundError:
        return None


def _tree_of(files: RepoFiles | None) -> RepoTree:
    return RepoTree(files.paths if files is not None else frozenset())


async def _read_at(files: RepoFiles | None, path: RepoPath, branch: str) -> FileContent | None:
    content = await files.read(path) if files is not None else None
    if files is None or content is None:
        return None
    return FileContent(path=path, ref=branch, content=content, last_commit_id=files.commit_id)


class GitLabSigsRepository:
    """The team repos of one sigs group."""

    def __init__(
        self,
        gitlab: GitLabPort,
        cache: TtlCache,
        snapshots: RepoSnapshots,
        *,
        group: str,
        branch: str,
        ttl: float,
    ) -> None:
        """Read ``group``'s projects at ``branch``; keep each read for ``ttl`` seconds."""
        self._gitlab = gitlab
        self._cache = cache
        self._snapshots = snapshots
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

        return await self._cache.get_or_fetch(
            cache_keys.teams(), fetch, ttl=self._ttl, stale=stale_for(self._ttl)
        )

    async def access(self, team: Team) -> AccessLevel:
        """See SigsRepository.access; kept like the team list, answered stale while refreshed."""
        pid = team.project.id
        return await self._cache.get_or_fetch(
            cache_keys.access(pid),
            lambda: self._gitlab.access_level(pid),
            ttl=self._ttl,
            stale=stale_for(self._ttl),
        )

    async def tree(self, team: Team) -> RepoTree:
        """See SigsRepository.tree (an empty repository has an empty tree)."""
        files = await self._snapshots.files(team.project.id, self._branch)
        return _tree_of(files)

    async def read(self, team: Team, path: RepoPath) -> FileContent | None:
        """See SigsRepository.read; ``last_commit_id`` is the commit it was read at (ADR-0035)."""
        files = await self._snapshots.files(team.project.id, self._branch)
        return await _read_at(files, path, self._branch)

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
        self._snapshots.forget(team.project.id)


class GitLabDay1Repository:
    """The day1 repo, read at the branch the platform reads (``main``)."""

    def __init__(
        self,
        gitlab: GitLabPort,
        cache: TtlCache,
        snapshots: RepoSnapshots,
        *,
        project: int | str,
        branch: str,
        ttl: float,
    ) -> None:
        """``project`` is an id or ``group/name`` path."""
        self._gitlab = gitlab
        self._cache = cache
        self._snapshots = snapshots
        self._project = project
        self._branch = branch
        self._ttl = ttl

    async def index(self) -> Day1Index:
        """See Day1Repository.index; built once per day1 commit."""
        project = await self._cache.get_or_fetch(
            cache_keys.day1_project(self._project),
            lambda: self._gitlab.get_project(self._project),
            ttl=self._ttl,
            stale=stale_for(self._ttl),
        )
        files = await self._snapshots.files(project.id, self._branch)

        async def build() -> Day1Index:
            tree = _tree_of(files)
            paths = day1_version_files(tree)
            read = await asyncio.gather(*(_read_at(files, p, self._branch) for p in paths))
            return build_day1_index(tree, {str(f.path): f.content for f in read if f is not None})

        commit = files.commit_id if files is not None else ""
        return await self._cache.get_or_fetch(
            cache_keys.day1_index(project.id, commit), build, ttl=self._ttl
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

    def on_this_gitlab(self, repo_url: str) -> bool:
        """See ChartRepository.on_this_gitlab."""
        return self.project_path(repo_url) is not None

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
