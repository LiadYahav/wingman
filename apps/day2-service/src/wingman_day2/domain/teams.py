"""Teams: every project directly in the sigs group is one (the scmProvider generator's rule)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from wingman_core.domain.git import Project, RepoPath
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
