"""Load repo trees from ``dev/gitlab-fixtures`` and seed a GitLab with them.

The fixture directory is ``<group>[/<subgroup>...]/<project>/<files...>``:
every top-level folder is a group, and below it a folder that holds a file
is a project while one that holds only folders is a subgroup
(``redbull/helm-charts/bmhgen``, ADR-0060). An optional
``branches.yaml`` at its root names extra branches per project, and an
optional ``access.yaml`` the role Wingman's account has on a project where it
is not the owner (``sigs/orca: reporter``). One loader feeds both the
in-memory fake (tests) and the real-GitLab seed script (local development),
so both start from the same state; a real GitLab seeded as root keeps root's
own access (the seed script says so).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from wingman_core.domain.git import AccessLevel
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab

_CHART_VERSION = re.compile(r"^version: .*$", re.MULTILINE)
_SEMVER_ISH = re.compile(r"^\d+\.\d+\.\d+")


@dataclass(frozen=True, slots=True)
class FixtureProject:
    """One project to create: its path, its default-branch files, and extra branches.

    Each extra branch starts as a copy of the default branch. In a chart repo
    a branch is a frozen release, so its ``Chart.yaml`` version is set to the
    branch name when that name looks like a version.
    """

    path_with_namespace: str
    files: Mapping[str, str]
    branches: tuple[str, ...] = ()
    access_level: AccessLevel | None = None
    """Wingman's account's role on the project; ``None``: it owns the project."""

    def branch_files(self, branch: str) -> dict[str, str]:
        """The files of one extra branch."""
        files = dict(self.files)
        chart = files.get("Chart.yaml")
        if chart is not None and _SEMVER_ISH.match(branch):
            files["Chart.yaml"] = _CHART_VERSION.sub(f"version: {branch}", chart, count=1)
        return files


def default_fixture_root() -> Path:
    """``dev/gitlab-fixtures`` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "dev" / "gitlab-fixtures"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("dev/gitlab-fixtures not found above this file")


def load_fixture_projects(
    root: Path, *, substitutions: Mapping[str, str] | None = None
) -> list[FixtureProject]:
    """Read every project under ``root``, in nested groups too.

    ``substitutions`` replaces ``{{KEY}}`` in file contents, e.g. ``GITLAB_URL``.
    """
    branches: dict[str, list[str]] = _read_yaml(root / "branches.yaml")
    access = {
        path: _access_level(path, role) for path, role in _read_yaml(root / "access.yaml").items()
    }
    projects: list[FixtureProject] = []
    for group in _folders(root):
        for project in _project_folders(group):
            path_with_namespace = project.relative_to(root).as_posix()
            files = {
                file.relative_to(project).as_posix(): _substitute(
                    file.read_text(encoding="utf-8"), substitutions
                )
                for file in sorted(project.rglob("*"))
                if _is_fixture_file(file)
            }
            projects.append(
                FixtureProject(
                    path_with_namespace,
                    files,
                    tuple(branches.get(path_with_namespace, ())),
                    access.pop(path_with_namespace, None),
                )
            )
    if access:
        raise ValueError(f"access.yaml names projects that are not fixtures: {sorted(access)}")
    unknown = sorted(set(branches) - {p.path_with_namespace for p in projects})
    if unknown:
        raise ValueError(f"branches.yaml names projects that are not fixtures: {unknown}")
    return projects


def _folders(parent: Path) -> list[Path]:
    return sorted(p for p in parent.iterdir() if p.is_dir() and not p.name.startswith("."))


def _is_fixture_file(path: Path) -> bool:
    return path.is_file() and path.name != ".DS_Store"


def _project_folders(group: Path) -> Iterator[Path]:
    """The projects below ``group``: a folder with a file is one, one of folders a subgroup."""
    for folder in _folders(group):
        if any(_is_fixture_file(entry) for entry in folder.iterdir()):
            yield folder
        else:
            yield from _project_folders(folder)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _access_level(path: str, role: object) -> AccessLevel:
    try:
        return AccessLevel[str(role).upper()]
    except KeyError:
        roles = ", ".join(level.role for level in AccessLevel)
        raise ValueError(f"access.yaml: {path}: {role!r} is not a role ({roles})") from None


def seed_fake(gitlab: InMemoryGitLab, projects: list[FixtureProject]) -> None:
    """Create every fixture project, with its branches, in the fake."""
    for fixture in projects:
        project = gitlab.create_project(fixture.path_with_namespace, fixture.files)
        if fixture.access_level is not None:
            gitlab.set_access_level(project.id, fixture.access_level)
        for branch in fixture.branches:
            gitlab.create_project_branch(project.id, branch, fixture.branch_files(branch))


def _substitute(text: str, substitutions: Mapping[str, str] | None) -> str:
    for key, value in (substitutions or {}).items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text
