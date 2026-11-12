"""The GitLabPort contract, run against the in-memory fake (every test run)."""

from __future__ import annotations

import itertools
from collections.abc import Mapping

import pytest

from wingman_core.domain.git import AccessLevel, Project
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.ports.gitlab import GitLabPort
from wingman_core.testing.gitlab_contract import (
    GitLabContract,
    NewMember,
    NewProject,
    RenameProject,
    Share,
)


class TestInMemoryGitLabContract(GitLabContract):
    @pytest.fixture
    def gitlab(self) -> InMemoryGitLab:
        return InMemoryGitLab()

    @pytest.fixture
    def new_project(self, gitlab: InMemoryGitLab) -> NewProject:
        counter = itertools.count(1)

        async def make(files: Mapping[str, str]) -> Project:
            return gitlab.create_project(f"contract/project-{next(counter)}", files)

        return make

    @pytest.fixture
    def rename_project(self, gitlab: InMemoryGitLab) -> RenameProject:
        async def rename(project: Project, name: str) -> None:
            namespace = project.path_with_namespace.rsplit("/", 1)[0]
            gitlab.rename_project(project.id, f"{namespace}/{name}")

        return rename

    @pytest.fixture
    def new_member(self, gitlab: InMemoryGitLab) -> NewMember:
        counter = itertools.count(1)

        async def make(
            project: Project,
            *,
            project_level: AccessLevel | None = None,
            group_level: AccessLevel | None = None,
            share: Share | None = None,
        ) -> GitLabPort:
            name = f"member-{next(counter)}"
            if group_level is not None:
                group = project.path_with_namespace.rsplit("/", 1)[0]
                gitlab.add_group_member(group, group_level, username=name)
            if project_level is not None:
                gitlab.set_access_level(project.id, project_level, username=name)
            if share is not None:
                parent = f"shares/{name}"
                gitlab.add_group_member(parent, share.role, username=name)
                shared = f"{parent}/child" if share.inherited else parent
                gitlab.share_project(project.id, shared, share.level)
            return gitlab.as_account(name)

        return make
