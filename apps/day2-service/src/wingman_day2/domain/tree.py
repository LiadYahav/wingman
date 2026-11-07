"""A repository's files at one commit, and the directory view Argo's generators see.

git stores no empty directories, so a directory exists exactly when some file
is below it: that is how a folder becomes "the registration" of a cluster or a
chart. Argo's ``directories:`` generators match one path segment per ``*``
(Go ``path.Match``); :meth:`RepoTree.subdirs` is that ``<path>/*``. Hidden
directories are skipped, as ``render_chain.py`` skips them.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from wingman_core.domain.git import ChangeKind, FileChange, RepoPath


def _hidden(path: str) -> bool:
    return any(segment.startswith(".") for segment in path.split("/"))


@dataclass(frozen=True, slots=True)
class RepoTree:
    """Every file path of a repository; directories are derived from them."""

    files: frozenset[str]
    _dirs: frozenset[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Derive the directories once."""
        dirs: set[str] = set()
        for file in self.files:
            parts = file.split("/")[:-1]
            dirs.update("/".join(parts[: i + 1]) for i in range(len(parts)))
        object.__setattr__(self, "_dirs", frozenset(dirs))

    @classmethod
    def of(cls, paths: Iterable[str | RepoPath]) -> RepoTree:
        """A tree holding ``paths`` (validated as repository paths)."""
        return cls(frozenset(str(RepoPath(str(p))) for p in paths))

    def is_file(self, path: RepoPath) -> bool:
        """Whether ``path`` is a file."""
        return str(path) in self.files

    def is_dir(self, path: RepoPath) -> bool:
        """Whether ``path`` is a (non-empty, hence existing) directory."""
        return path.is_root or str(path) in self._dirs

    def subdirs(self, path: RepoPath) -> list[str]:
        """Names of the visible directories directly in ``path``: a ``<path>/*`` generator."""
        if _hidden(str(path)):
            return []
        prefix = "" if path.is_root else f"{path}/"
        names = {
            d[len(prefix) :]
            for d in self._dirs
            if d.startswith(prefix) and "/" not in d[len(prefix) :]
        }
        return sorted(name for name in names if not name.startswith("."))

    def files_under(self, path: RepoPath) -> list[RepoPath]:
        """Every file at or below ``path``, hidden ones too (what removing a folder deletes)."""
        return sorted(RepoPath(f) for f in self.files if RepoPath(f).is_within(path))

    def with_changes(self, changes: Iterable[FileChange]) -> RepoTree:
        """The tree after ``changes`` are committed."""
        files = set(self.files)
        for change in changes:
            if change.kind is ChangeKind.DELETE:
                files.discard(str(change.path))
            elif change.kind is ChangeKind.MOVE and change.previous_path is not None:
                files.discard(str(change.previous_path))
                files.add(str(change.path))
            else:
                files.add(str(change.path))
        return RepoTree(frozenset(files))
