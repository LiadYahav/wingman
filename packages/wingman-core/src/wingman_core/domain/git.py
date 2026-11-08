"""Git hosting value objects: projects, paths, files, commits and diffs.

These are the only types that cross the GitLabPort boundary. Adapters build
them from backend responses; application code never handles raw JSON.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from wingman_core.domain.errors import InvalidRepoPathError
from wingman_core.domain.users import User

_FORBIDDEN_SEGMENTS = frozenset({"", ".", ".."})


@dataclass(frozen=True, slots=True, order=True)
class RepoPath:
    """A normalized path inside a repository.

    Relative, ``/``-separated, with no empty, ``.`` or ``..`` segments. The
    empty string is the repository root. Building paths through this type is
    what stops a user-supplied name (a cluster, a team) from escaping the
    directory it is meant for.
    """

    value: str

    def __post_init__(self) -> None:
        """Reject anything that is not a normalized relative path."""
        if self.value == "":
            return
        if "\x00" in self.value or "\\" in self.value:
            raise InvalidRepoPathError(f"invalid character in repository path {self.value!r}")
        if any(segment in _FORBIDDEN_SEGMENTS for segment in self.value.split("/")):
            raise InvalidRepoPathError(f"not a normalized repository path: {self.value!r}")

    @classmethod
    def root(cls) -> RepoPath:
        """The repository root."""
        return cls("")

    @classmethod
    def of(cls, *segments: str) -> RepoPath:
        """Join segments into a path, validating each one.

        A segment may not contain ``/``: ``RepoPath.of("sites", site)`` can never
        reach outside ``sites/`` whatever ``site`` holds.
        """
        for segment in segments:
            if "/" in segment or segment in _FORBIDDEN_SEGMENTS:
                raise InvalidRepoPathError(f"invalid path segment {segment!r}")
        return cls("/".join(segments))

    @property
    def is_root(self) -> bool:
        """Whether this is the repository root."""
        return self.value == ""

    @property
    def name(self) -> str:
        """The last segment (``values.yaml`` for ``a/b/values.yaml``)."""
        return self.value.rsplit("/", 1)[-1]

    @property
    def parent(self) -> RepoPath:
        """The containing directory; the root's parent is the root."""
        if "/" not in self.value:
            return RepoPath.root()
        return RepoPath(self.value.rsplit("/", 1)[0])

    @property
    def parts(self) -> tuple[str, ...]:
        """The segments, root first; empty for the root."""
        return () if self.is_root else tuple(self.value.split("/"))

    def child(self, *segments: str) -> RepoPath:
        """This path extended by validated segments."""
        tail = RepoPath.of(*segments)
        if self.is_root:
            return tail
        return RepoPath(f"{self.value}/{tail.value}")

    def is_within(self, directory: RepoPath) -> bool:
        """Whether this path is ``directory`` itself or below it."""
        if directory.is_root:
            return True
        return self.value == directory.value or self.value.startswith(f"{directory.value}/")

    def __str__(self) -> str:
        """The path as GitLab expects it."""
        return self.value


@dataclass(frozen=True, slots=True)
class Project:
    """A Git hosting project (a repository)."""

    id: int
    path_with_namespace: str
    default_branch: str
    web_url: str


class EntryKind(StrEnum):
    """What a tree entry is; the values are GitLab's."""

    FILE = "blob"
    DIRECTORY = "tree"


@dataclass(frozen=True, slots=True)
class TreeEntry:
    """One entry of a repository tree listing."""

    path: RepoPath
    kind: EntryKind

    @property
    def name(self) -> str:
        """The entry's own name."""
        return self.path.name


@dataclass(frozen=True, slots=True)
class FileContent:
    """A file read at a ref.

    ``last_commit_id`` is the last commit that changed this file. Passing it
    back on an update makes the write fail if the file changed in between
    (ADR-0006).
    """

    path: RepoPath
    ref: str
    content: str
    last_commit_id: str


class ChangeKind(StrEnum):
    """What a commit does to one file; the values are GitLab's commit actions."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    MOVE = "move"


@dataclass(frozen=True, slots=True)
class FileChange:
    """One file change inside a commit. Build it with the class methods."""

    kind: ChangeKind
    path: RepoPath
    content: str | None = None
    previous_path: RepoPath | None = None
    last_commit_id: str | None = None

    def __post_init__(self) -> None:
        """Reject combinations no backend accepts."""
        needs_content = self.kind in (ChangeKind.CREATE, ChangeKind.UPDATE)
        if needs_content and self.content is None:
            raise ValueError(f"a {self.kind} change needs content")
        if self.kind is ChangeKind.DELETE and self.content is not None:
            raise ValueError("a delete change carries no content")
        if (self.kind is ChangeKind.MOVE) != (self.previous_path is not None):
            raise ValueError("previous_path is required for a move and only for a move")
        if self.path.is_root:
            raise ValueError("a change needs a file path, not the repository root")

    @classmethod
    def create(cls, path: RepoPath, content: str) -> FileChange:
        """Add a new file; fails if it exists."""
        return cls(ChangeKind.CREATE, path, content=content)

    @classmethod
    def update(cls, path: RepoPath, content: str, *, last_commit_id: str | None) -> FileChange:
        """Replace a file's content, guarded by the commit it was read at."""
        return cls(ChangeKind.UPDATE, path, content=content, last_commit_id=last_commit_id)

    @classmethod
    def delete(cls, path: RepoPath, *, last_commit_id: str | None = None) -> FileChange:
        """Remove a file; fails if it does not exist."""
        return cls(ChangeKind.DELETE, path, last_commit_id=last_commit_id)

    @classmethod
    def move(
        cls, previous_path: RepoPath, path: RepoPath, content: str | None = None
    ) -> FileChange:
        """Rename a file, optionally changing its content."""
        return cls(ChangeKind.MOVE, path, content=content, previous_path=previous_path)


@dataclass(frozen=True, slots=True)
class CommitAuthor:
    """Who a commit is authored by, when that is not the account making it.

    Wingman commits with its service account's token; passing the requesting
    user here makes Git history (and the audit view) name the person, while
    GitLab still records the service account as the committer.
    """

    name: str
    email: str

    def __post_init__(self) -> None:
        """Reject values GitLab would refuse or that would forge a header line."""
        for value in (self.name, self.email):
            if not value.strip() or any(c in value for c in "\r\n<>"):
                raise ValueError(f"invalid commit author field {value!r}")


COMMIT_EMAIL_DOMAIN: Final = "openshift.local"
"""As the legacy service: ``<username>@openshift.local``, an address that receives nothing."""
_NOT_IN_AUTHOR = re.compile(r"[\r\n<>]+")


def commit_author(user: User) -> CommitAuthor:
    """The Git author of a change ``user`` asked for (GitLab keeps the bot as committer)."""
    username = _NOT_IN_AUTHOR.sub("-", user.username).strip() or "unknown"
    name = _NOT_IN_AUTHOR.sub(" ", user.full_name).strip() or username
    return CommitAuthor(name=name, email=f"{username}@{COMMIT_EMAIL_DOMAIN}")


@dataclass(frozen=True, slots=True)
class Commit:
    """A commit, as listed in history."""

    id: str
    short_id: str
    title: str
    message: str
    author_name: str
    author_email: str
    authored_at: datetime
    web_url: str
    parent_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FileDiff:
    """How one file differs between two revisions. ``diff`` is a unified diff."""

    old_path: RepoPath
    new_path: RepoPath
    new_file: bool
    deleted_file: bool
    renamed_file: bool
    diff: str


@dataclass(frozen=True, slots=True)
class Branch:
    """A branch and the commit it points at."""

    name: str
    commit_id: str


def tree_of(paths: Iterable[str], path: RepoPath, *, recursive: bool) -> list[TreeEntry] | None:
    """``list_tree`` from a set of file paths: files and the directories they imply, sorted.

    ``None`` when nothing is at or under ``path`` (a missing directory; at the
    root, an empty repository). Git keeps no empty directories, so the
    directories implied by the files are exactly the repository's.
    """
    prefix = "" if path.is_root else f"{path}/"
    found: dict[str, EntryKind] = {}
    for file in paths:
        if not file.startswith(prefix):
            continue
        parts = file[len(prefix) :].split("/")
        if recursive:
            for depth in range(1, len(parts)):
                found[prefix + "/".join(parts[:depth])] = EntryKind.DIRECTORY
            found[file] = EntryKind.FILE
        else:
            found[prefix + parts[0]] = EntryKind.FILE if len(parts) == 1 else EntryKind.DIRECTORY
    if not found:
        return None
    return sorted((TreeEntry(RepoPath(p), kind) for p, kind in found.items()), key=lambda e: e.path)


@dataclass(frozen=True, slots=True)
class RepoArchive:
    """Every file of a repository at one commit, from one archive download.

    ``files`` maps each path to its bytes; a symlink holds its target path,
    as ``read_file`` returns it. Submodules are not in it.
    """

    commit_id: str
    files: Mapping[str, bytes]

    @property
    def size(self) -> int:
        """The bytes of every file together."""
        return sum(len(content) for content in self.files.values())
