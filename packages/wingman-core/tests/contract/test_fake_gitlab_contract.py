"""The GitLabPort contract, run against the in-memory fake (every test run)."""

from __future__ import annotations

import itertools
from collections.abc import Mapping

import pytest

from wingman_core.domain.errors import NotFoundError
from wingman_core.domain.git import FileChange, Project, RepoPath
from wingman_core.domain.merge_request import MergeRequestRef, NewMergeRequest
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.testing.gitlab_contract import GitLabContract, NewProject, RenameProject


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


async def test_the_fake_keeps_each_merge_requests_comments_in_order() -> None:
    # Only the fake can show a comment back: the port has no read for notes.
    gitlab = InMemoryGitLab()
    project = gitlab.create_project("g/p", {"a.yaml": "a: 1\n"})
    await gitlab.commit(
        project.id,
        branch="b1",
        start_branch="main",
        message="change",
        changes=[FileChange.update(RepoPath("a.yaml"), "a: 2\n", last_commit_id=None)],
    )
    mr = await gitlab.create_merge_request(project.id, NewMergeRequest("b1", "main", "t"))
    assert gitlab.notes(mr.ref) == []
    await gitlab.comment_on_merge_request(mr.ref, "first")
    await gitlab.close_merge_request(mr.ref)
    await gitlab.comment_on_merge_request(mr.ref, "second")
    assert gitlab.notes(mr.ref) == ["first", "second"]
    with pytest.raises(NotFoundError):
        gitlab.notes(MergeRequestRef(project.id, 99))
