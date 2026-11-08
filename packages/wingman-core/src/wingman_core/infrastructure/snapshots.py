"""RepoSnapshots: a repository's files at its branch head, read once per commit (ADR-0035).

Reading file by file cost one GitLab call per file and one per 100 tree
entries, and the TTL cache (ADR-0011) forgot it all every few seconds. Here a
repository costs one call per TTL to see where its branch points, plus one
archive download when the branch has moved. A commit's files never change, so
they are kept until the branch moves on. Every page reads one commit per
repository, never a mix of two.

A repository larger than the archive budget, or one GitLab will not archive
(a 429 from its archive rate limit, an unexpected answer), is read file by
file at the same commit, each file once.

A file read here carries the snapshot's commit as its ``last_commit_id``.
GitLab's guard compares the file's last change as of that commit with its last
change on the branch, so the guarded writes of ADR-0006 work unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Final, Protocol

from wingman_core.domain.errors import GitError, InvalidRequestError, NotFoundError
from wingman_core.domain.git import EntryKind, RepoArchive, RepoPath
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.ports.gitlab import GitLabPort

logger = logging.getLogger(__name__)

MAX_ARCHIVE_BYTES: Final = 64 * 1024 * 1024
"""One repository's files; above it the repository is read file by file."""
MAX_HELD_BYTES: Final = 128 * 1024 * 1024
"""Every archive held, together; the least recently used goes first. A pod has 512 MiB."""


class RepoFiles(Protocol):
    """Every file of a repository at one commit."""

    @property
    def commit_id(self) -> str:
        """The commit the files are at."""
        ...

    @property
    def paths(self) -> frozenset[str]:
        """Every file's path (no directories)."""
        ...

    @property
    def size(self) -> int:
        """The bytes held in memory, counted against :data:`MAX_HELD_BYTES`."""
        ...

    async def read(self, path: RepoPath) -> str | None:
        """The file's text, ``None`` if there is no such file; InvalidRequestError if not UTF-8."""
        ...


def _text(content: bytes, path: RepoPath, commit_id: str) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidRequestError(f"{path} at {commit_id[:8]} is not UTF-8 text") from exc


class _ArchiveFiles:
    """The files of one archive download, in memory."""

    def __init__(self, archive: RepoArchive) -> None:
        self._archive = archive
        self._paths = frozenset(archive.files)

    @property
    def commit_id(self) -> str:
        return self._archive.commit_id

    @property
    def paths(self) -> frozenset[str]:
        return self._paths

    @property
    def size(self) -> int:
        return self._archive.size

    async def read(self, path: RepoPath) -> str | None:
        content = self._archive.files.get(str(path))
        return None if content is None else _text(content, path, self.commit_id)


class _FileByFile:
    """The fallback: the tree at the commit, and each file read once when asked for."""

    def __init__(
        self, gitlab: GitLabPort, project_id: int, commit_id: str, paths: frozenset[str]
    ) -> None:
        self._gitlab = gitlab
        self._project_id = project_id
        self._commit_id = commit_id
        self._paths = paths
        self._read: dict[str, asyncio.Task[str]] = {}

    @classmethod
    async def load(cls, gitlab: GitLabPort, project_id: int, commit_id: str) -> _FileByFile:
        entries = await gitlab.list_tree(project_id, RepoPath.root(), commit_id, recursive=True)
        paths = frozenset(str(e.path) for e in entries if e.kind is EntryKind.FILE)
        return cls(gitlab, project_id, commit_id, paths)

    @property
    def commit_id(self) -> str:
        return self._commit_id

    @property
    def paths(self) -> frozenset[str]:
        return self._paths

    @property
    def size(self) -> int:
        return 0  # what it reads is a few files, not the repository

    async def read(self, path: RepoPath) -> str | None:
        key = str(path)
        if key not in self._paths:
            return None
        task = self._read.get(key)
        if task is None:
            task = asyncio.ensure_future(self._fetch(path))
            self._read[key] = task
        try:
            return await asyncio.shield(task)
        except BaseException:
            if self._read.get(key) is task and task.done():
                del self._read[key]  # a failed read is not kept
            raise

    async def _fetch(self, path: RepoPath) -> str:
        return (await self._gitlab.read_file(self._project_id, path, self._commit_id)).content


class RepoSnapshots:
    """Each project's files at a branch's head, shared by every reader of one service."""

    def __init__(
        self,
        gitlab: GitLabPort,
        cache: TtlCache,
        *,
        ttl: float,
        max_archive_bytes: int = MAX_ARCHIVE_BYTES,
        max_held_bytes: int = MAX_HELD_BYTES,
    ) -> None:
        """Check a branch's head at most every ``ttl`` seconds (ADR-0011's TTL)."""
        self._gitlab = gitlab
        self._cache = cache
        self._ttl = ttl
        self._max_archive_bytes = max_archive_bytes
        self._max_held_bytes = max_held_bytes
        self._held: OrderedDict[tuple[int, str], RepoFiles] = OrderedDict()
        self._loading: dict[tuple[int, str], asyncio.Task[RepoFiles]] = {}

    @staticmethod
    def _head_key(project_id: int, branch: str = "") -> str:
        return f"snapshot-head:{project_id}:{branch}"

    async def head(self, project_id: int, branch: str) -> str | None:
        """The commit ``branch`` points at, ``None`` if it does not exist (an empty repository)."""

        async def fetch() -> str | None:
            try:
                return (await self._gitlab.get_branch(project_id, branch)).commit_id
            except NotFoundError:
                return None

        return await self._cache.get_or_fetch(
            self._head_key(project_id, branch), fetch, ttl=self._ttl
        )

    async def files(self, project_id: int, branch: str) -> RepoFiles | None:
        """Every file at ``branch``'s head, ``None`` if the branch does not exist."""
        commit_id = await self.head(project_id, branch)
        return None if commit_id is None else await self.at(project_id, commit_id)

    async def at(self, project_id: int, commit_id: str) -> RepoFiles:
        """Every file at ``commit_id`` (a full commit id)."""
        key = (project_id, commit_id)
        held = self._held.get(key)
        if held is not None:
            self._held.move_to_end(key)
            return held
        task = self._loading.get(key)
        if task is None:
            task = asyncio.ensure_future(self._load(project_id, commit_id))
            self._loading[key] = task
            task.add_done_callback(lambda _: self._loading.pop(key, None))
        return await asyncio.shield(task)

    def forget(self, project_id: int) -> None:
        """Look at the project's branches again on the next read (after Wingman wrote to it)."""
        self._cache.invalidate_prefix(self._head_key(project_id))

    async def _load(self, project_id: int, commit_id: str) -> RepoFiles:
        files: RepoFiles
        try:
            archive = await self._gitlab.read_archive(
                project_id, commit_id, max_bytes=self._max_archive_bytes
            )
            files = _ArchiveFiles(archive)
        except GitError as exc:
            logger.warning(
                "reading project %s at %s file by file: its archive failed (%s)",
                project_id,
                commit_id[:8],
                exc,
            )
            files = await _FileByFile.load(self._gitlab, project_id, commit_id)
        self._hold((project_id, commit_id), files)
        return files

    def _hold(self, key: tuple[int, str], files: RepoFiles) -> None:
        # A project is read at one branch per service: an older commit of it is not needed again.
        for old in [k for k in self._held if k[0] == key[0]]:
            del self._held[old]
        self._held[key] = files
        while (
            len(self._held) > 1 and sum(f.size for f in self._held.values()) > self._max_held_bytes
        ):
            self._held.popitem(last=False)
