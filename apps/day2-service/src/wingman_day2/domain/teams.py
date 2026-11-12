"""Teams: every project directly in the sigs group is one (the scmProvider generator's rule).

A team opts in to Wingman's writes by giving Wingman's GitLab account write
access to its own project (Developer or higher: push a branch, open an MR).
Without it, the team is read-only in Wingman (ADR-0043).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from wingman_core.domain.git import AccessLevel, ChangeKind, FileChange, Project, RepoPath
from wingman_day2.domain import layout
from wingman_day2.domain.clusters import DefaultsScope
from wingman_day2.domain.tree import RepoTree


@dataclass(frozen=True, slots=True)
class Team:
    """A team and its repo. The name is the project's own path, as Argo names it."""

    name: str
    project: Project

    @classmethod
    def of(cls, project: Project) -> Team:
        """The team a sigs-group project is."""
        return cls(project.path_with_namespace.rsplit("/", 1)[-1], project)


WRITE_LEVEL = AccessLevel.DEVELOPER
"""The least access that lets Wingman push a branch and open a merge request."""


@dataclass(frozen=True, slots=True)
class TeamAccess:
    """What Wingman's GitLab account may do in a team's project."""

    team: str
    project: str
    level: AccessLevel

    @property
    def writable(self) -> bool:
        """Whether Wingman may open merge requests for the team."""
        return self.level >= WRITE_LEVEL

    @property
    def reason(self) -> str | None:
        """Why the team is read-only, in one sentence; ``None`` when it is writable."""
        if self.writable:
            return None
        has = (
            "is not a member there"
            if self.level is AccessLevel.NONE
            else f"is {_article(self.level.role)} {self.level.role.capitalize()} there"
        )
        return (
            f"{self.team} hasn't given Wingman write access to {self.project}: Wingman's GitLab "
            f"account {has}, and opening a merge request needs Developer or higher. A maintainer "
            f"of {self.project} turns writes on by adding the account to the project as a "
            "Developer."
        )


def _article(word: str) -> str:
    return "an" if word[:1] in "aeiou" else "a"


@dataclass(frozen=True, slots=True)
class TeamRepo:
    """A team repo as the platform's generators see it: the tree plus its control files.

    ``files`` holds the text of the files read at generation time rather than
    by a leaf: ``defaults/<scope>/exclusions.yaml`` and UPI ``version.yaml``s
    (see :func:`control_files`).
    """

    team: str
    tree: RepoTree
    files: Mapping[str, str] = field(default_factory=dict)

    def with_changes(self, changes: Iterable[FileChange]) -> TeamRepo:
        """The repo after ``changes``: its tree, and its control files' text as committed."""
        changes = list(changes)
        tree = self.tree.with_changes(changes)
        files = dict(self.files)
        for change in changes:
            path = str(change.path)
            if change.kind is ChangeKind.DELETE:
                files.pop(path, None)
                continue
            moved = None
            if change.previous_path is not None:
                moved = files.pop(str(change.previous_path), None)
            content = change.content if change.content is not None else moved
            if content is not None:
                files[path] = content
        wanted = {str(p) for p in control_files(tree)}
        return TeamRepo(self.team, tree, {k: v for k, v in files.items() if k in wanted})


def control_files(tree: RepoTree) -> list[RepoPath]:
    """The existing control files of ``tree``: exclusion matrices and UPI version files."""
    paths = [
        layout.exclusions_file(scope)
        for scope in DefaultsScope
        if tree.is_file(layout.exclusions_file(scope))
    ]
    sites = RepoPath.of(layout.SITES)
    for site in tree.subdirs(sites):
        for env in tree.subdirs(sites.child(site)):
            upi = sites.child(site, env, layout.UPI)
            for cluster in tree.subdirs(upi):
                version = upi.child(cluster, layout.VERSION_FILE)
                if tree.is_file(version):
                    paths.append(version)
    return paths
