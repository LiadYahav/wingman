"""Load repo trees from ``dev/gitlab-fixtures`` and seed a GitLab with them.

The fixture directory is ``<group>/<project>/<files...>``; an optional
``branches.yaml`` at its root names extra branches per project. One loader
feeds both the in-memory fake (tests) and the real-GitLab seed script (local
development), so both start from the same state.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

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
    """Read every ``<group>/<project>`` under ``root``.

    ``substitutions`` replaces ``{{KEY}}`` in file contents, e.g. ``GITLAB_URL``.
    """
    branches_file = root / "branches.yaml"
    branches: dict[str, list[str]] = (
        yaml.safe_load(branches_file.read_text(encoding="utf-8")) or {}
        if branches_file.exists()
        else {}
    )
    projects: list[FixtureProject] = []
    for group in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for project in sorted(p for p in group.iterdir() if p.is_dir()):
            path_with_namespace = f"{group.name}/{project.name}"
            files = {
                file.relative_to(project).as_posix(): _substitute(
                    file.read_text(encoding="utf-8"), substitutions
                )
                for file in sorted(project.rglob("*"))
                if file.is_file() and file.name != ".DS_Store"
            }
            projects.append(
                FixtureProject(
                    path_with_namespace, files, tuple(branches.get(path_with_namespace, ()))
                )
            )
    return projects


def seed_fake(gitlab: InMemoryGitLab, projects: list[FixtureProject]) -> None:
    """Create every fixture project, with its branches, in the fake."""
    for fixture in projects:
        project = gitlab.create_project(fixture.path_with_namespace, fixture.files)
        for branch in fixture.branches:
            gitlab.create_project_branch(project.id, branch, fixture.branch_files(branch))


def _substitute(text: str, substitutions: Mapping[str, str] | None) -> str:
    for key, value in (substitutions or {}).items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text
