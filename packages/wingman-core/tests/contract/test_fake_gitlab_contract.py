"""The GitLabPort contract, run against the in-memory fake (every test run)."""

from __future__ import annotations

import itertools
from collections.abc import Mapping

import pytest

from wingman_core.domain.git import Project
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.testing.gitlab_contract import GitLabContract, NewProject


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
