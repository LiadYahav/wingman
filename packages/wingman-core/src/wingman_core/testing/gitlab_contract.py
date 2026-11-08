"""The GitLabPort contract: behaviour every implementation must have (ADR-0005).

Subclass :class:`GitLabContract` in a test module and provide two fixtures:

- ``gitlab``: the GitLabPort under test;
- ``new_project``: an async factory ``(files) -> Project`` that creates a
  fresh project whose default branch ``main`` holds ``files``;
- ``rename_project``: an async ``(project, name) -> None`` that gives the
  project a new last path segment, as a GitLab rename does.

The suite runs against the in-memory fake on every test run and against a
real GitLab when one is configured. A failure on the real one means the fake
has drifted from GitLab: fix the fake (and this suite) first.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

import pytest

from wingman_core.domain.errors import (
    AlreadyExistsError,
    InvalidRequestError,
    NotFoundError,
    NotMergeableError,
    RevisionConflictError,
)
from wingman_core.domain.git import CommitAuthor, EntryKind, FileChange, Project, RepoPath
from wingman_core.domain.merge_request import MergeRequestRef, MRState, NewMergeRequest
from wingman_core.ports.gitlab import GitLabPort

NewProject = Callable[[Mapping[str, str]], Awaitable[Project]]
RenameProject = Callable[[Project, str], Awaitable[None]]

FILES = {
    "README.md": "# fixture\n",
    "sites/site1/values.yaml": "a: 1\n",
    "sites/site1/mces/mce-a/values.yaml": "b: 2\n",
}


def _p(path: str) -> RepoPath:
    return RepoPath(path)


async def _branch_with_change(
    gitlab: GitLabPort, project: Project, branch: str, path: str, content: str
) -> None:
    await gitlab.commit(
        project.id,
        branch=branch,
        start_branch="main",
        message=f"change {path}",
        changes=[FileChange.update(_p(path), content, last_commit_id=None)],
    )


class GitLabContract:
    """Behaviour tests for any GitLabPort. Not collected itself; subclass it."""

    # ── Files and trees ─────────────────────────────────────────────────────

    async def test_read_file_returns_content_and_last_commit(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        file = await gitlab.read_file(project.id, _p("sites/site1/values.yaml"), "main")
        assert file.content == "a: 1\n"
        assert len(file.last_commit_id) == 40

    async def test_read_missing_file_is_not_found(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        with pytest.raises(NotFoundError):
            await gitlab.read_file(project.id, _p("nope.yaml"), "main")

    async def test_list_tree_lists_direct_children_sorted(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        entries = await gitlab.list_tree(project.id, _p("sites/site1"), "main")
        assert [(str(e.path), e.kind) for e in entries] == [
            ("sites/site1/mces", EntryKind.DIRECTORY),
            ("sites/site1/values.yaml", EntryKind.FILE),
        ]

    async def test_list_tree_recursive_includes_nested_entries(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        entries = await gitlab.list_tree(project.id, _p("sites"), "main", recursive=True)
        assert [str(e.path) for e in entries] == [
            "sites/site1",
            "sites/site1/mces",
            "sites/site1/mces/mce-a",
            "sites/site1/mces/mce-a/values.yaml",
            "sites/site1/values.yaml",
        ]

    async def test_list_tree_of_missing_directory_is_not_found(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        with pytest.raises(NotFoundError):
            await gitlab.list_tree(project.id, _p("sites/site9"), "main")

    # ── Commits ─────────────────────────────────────────────────────────────

    async def test_create_of_existing_file_is_already_exists(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        with pytest.raises(AlreadyExistsError):
            await gitlab.commit(
                project.id,
                branch="main",
                message="dup",
                changes=[FileChange.create(_p("README.md"), "x")],
            )

    async def test_update_of_missing_file_is_not_found(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        with pytest.raises(NotFoundError):
            await gitlab.commit(
                project.id,
                branch="main",
                message="update",
                changes=[FileChange.update(_p("missing.yaml"), "x", last_commit_id=None)],
            )

    async def test_update_with_current_last_commit_id_succeeds(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        file = await gitlab.read_file(project.id, _p("README.md"), "main")
        await gitlab.commit(
            project.id,
            branch="main",
            message="edit",
            changes=[
                FileChange.update(file.path, "# edited\n", last_commit_id=file.last_commit_id)
            ],
        )
        assert (await gitlab.read_file(project.id, file.path, "main")).content == "# edited\n"

    async def test_update_with_stale_last_commit_id_is_revision_conflict(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        stale = await gitlab.read_file(project.id, _p("README.md"), "main")
        await gitlab.commit(
            project.id,
            branch="main",
            message="someone else",
            changes=[
                FileChange.update(stale.path, "# theirs\n", last_commit_id=stale.last_commit_id)
            ],
        )
        with pytest.raises(RevisionConflictError):
            await gitlab.commit(
                project.id,
                branch="main",
                message="mine",
                changes=[
                    FileChange.update(stale.path, "# mine\n", last_commit_id=stale.last_commit_id)
                ],
            )
        assert (await gitlab.read_file(project.id, stale.path, "main")).content == "# theirs\n"

    async def test_commit_is_atomic(self, gitlab: GitLabPort, new_project: NewProject) -> None:
        project = await new_project(FILES)
        with pytest.raises(AlreadyExistsError):
            await gitlab.commit(
                project.id,
                branch="main",
                message="half",
                changes=[
                    FileChange.create(_p("new.yaml"), "x"),
                    FileChange.create(_p("README.md"), "x"),
                ],
            )
        with pytest.raises(NotFoundError):
            await gitlab.read_file(project.id, _p("new.yaml"), "main")

    async def test_commit_with_start_branch_creates_the_branch(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        await gitlab.commit(
            project.id,
            branch="feature",
            start_branch="main",
            message="add",
            changes=[FileChange.create(_p("added.yaml"), "c: 3\n")],
        )
        assert (await gitlab.read_file(project.id, _p("added.yaml"), "feature")).content == "c: 3\n"
        with pytest.raises(NotFoundError):
            await gitlab.read_file(project.id, _p("added.yaml"), "main")
        assert "feature" in [b.name for b in await gitlab.list_branches(project.id)]

    async def test_commit_author_is_recorded_in_history(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        author = CommitAuthor("Jane Doe", "jane.doe@example.invalid")
        made = await gitlab.commit(
            project.id,
            branch="feature",
            start_branch="main",
            message="authored",
            changes=[FileChange.create(_p("authored.yaml"), "d: 4\n")],
            author=author,
        )
        assert (made.author_name, made.author_email) == (author.name, author.email)
        listed = await gitlab.get_commit(project.id, made.id)
        assert (listed.author_name, listed.author_email) == (author.name, author.email)

    async def test_commit_to_missing_branch_is_not_found(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        with pytest.raises(NotFoundError):
            await gitlab.commit(
                project.id,
                branch="ghost",
                message="x",
                changes=[FileChange.create(_p("x.yaml"), "x")],
            )

    async def test_delete_and_move(self, gitlab: GitLabPort, new_project: NewProject) -> None:
        project = await new_project(FILES)
        await gitlab.commit(
            project.id,
            branch="main",
            message="reshape",
            changes=[
                FileChange.delete(_p("README.md")),
                FileChange.move(_p("sites/site1/values.yaml"), _p("sites/site2/values.yaml")),
            ],
        )
        with pytest.raises(NotFoundError):
            await gitlab.read_file(project.id, _p("README.md"), "main")
        moved = await gitlab.read_file(project.id, _p("sites/site2/values.yaml"), "main")
        assert moved.content == "a: 1\n"

    async def test_create_existing_branch_is_already_exists(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        await gitlab.create_branch(project.id, "dup", "main")
        with pytest.raises(AlreadyExistsError):
            await gitlab.create_branch(project.id, "dup", "main")

    async def test_list_commits_is_newest_first_and_filters_by_path(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        await gitlab.commit(
            project.id,
            branch="main",
            message="touch site1",
            changes=[
                FileChange.update(_p("sites/site1/values.yaml"), "a: 2\n", last_commit_id=None)
            ],
        )
        await gitlab.commit(
            project.id,
            branch="main",
            message="touch readme",
            changes=[FileChange.update(_p("README.md"), "# 2\n", last_commit_id=None)],
        )
        titles = [c.title for c in await gitlab.list_commits(project.id, ref="main")]
        assert titles[:2] == ["touch readme", "touch site1"]
        site1 = await gitlab.list_commits(project.id, ref="main", path=_p("sites/site1"))
        assert "touch readme" not in [c.title for c in site1]
        assert site1[0].title == "touch site1"

    async def test_commit_diff_describes_the_change(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        commit = await gitlab.commit(
            project.id,
            branch="main",
            message="edit",
            changes=[FileChange.update(_p("README.md"), "# changed\n", last_commit_id=None)],
        )
        assert (await gitlab.get_commit(project.id, commit.id)).title == "edit"
        [diff] = await gitlab.commit_diff(project.id, commit.id)
        assert str(diff.new_path) == "README.md"
        assert "+# changed" in diff.diff
        assert not diff.new_file

    # ── Merge requests ──────────────────────────────────────────────────────

    async def test_merge_request_iids_are_per_project(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        first, second = await new_project(FILES), await new_project(FILES)
        refs = []
        for project in (first, second):
            await _branch_with_change(gitlab, project, "b1", "README.md", "# b1\n")
            mr = await gitlab.create_merge_request(project.id, NewMergeRequest("b1", "main", "one"))
            refs.append(mr.ref)
        assert refs[0].iid == refs[1].iid
        assert refs[0] != refs[1]

    async def test_second_open_mr_for_a_branch_is_already_exists(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        await _branch_with_change(gitlab, project, "b1", "README.md", "# b1\n")
        await gitlab.create_merge_request(project.id, NewMergeRequest("b1", "main", "first"))
        with pytest.raises(AlreadyExistsError):
            await gitlab.create_merge_request(project.id, NewMergeRequest("b1", "main", "second"))

    async def test_list_merge_requests_filters_by_state_and_labels(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        for branch, labels in (
            ("b1", ("wingman", "day1")),
            ("b2", ("wingman",)),
            ("b3", ("other",)),
        ):
            await _branch_with_change(gitlab, project, branch, "README.md", f"# {branch}\n")
            await gitlab.create_merge_request(
                project.id, NewMergeRequest(branch, "main", branch, labels=labels)
            )
        wingman = await gitlab.list_merge_requests(project.id, labels=("wingman",))
        assert sorted(mr.source_branch for mr in wingman) == ["b1", "b2"]
        day1 = await gitlab.list_merge_requests(project.id, labels=("wingman", "day1"))
        assert [mr.source_branch for mr in day1] == ["b1"]
        await gitlab.close_merge_request(day1[0].ref)
        opened = await gitlab.list_merge_requests(project.id, labels=("wingman",))
        assert [mr.source_branch for mr in opened] == ["b2"]
        closed = await gitlab.list_merge_requests(project.id, state=MRState.CLOSED)
        assert [mr.source_branch for mr in closed] == ["b1"]

    async def test_merge_request_diff_lists_changed_files(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        await _branch_with_change(gitlab, project, "b1", "sites/site1/values.yaml", "a: 9\n")
        mr = await gitlab.create_merge_request(project.id, NewMergeRequest("b1", "main", "diff"))
        [diff] = await gitlab.merge_request_diff(mr.ref)
        assert str(diff.new_path) == "sites/site1/values.yaml"
        assert "+a: 9" in diff.diff

    async def test_merged_mr_keeps_its_diff(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        # GitLab removes the source branch in a background job after the
        # merge, so the diff must not depend on the branch still existing.
        project = await new_project(FILES)
        await _branch_with_change(gitlab, project, "b1", "README.md", "# kept\n")
        mr = await gitlab.create_merge_request(project.id, NewMergeRequest("b1", "main", "keep"))
        await gitlab.merge_merge_request(mr.ref)
        [diff] = await gitlab.merge_request_diff(mr.ref)
        assert "+# kept" in diff.diff

    async def test_approve_then_merge_changes_the_target_branch(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        await _branch_with_change(gitlab, project, "b1", "README.md", "# merged\n")
        mr = await gitlab.create_merge_request(
            project.id, NewMergeRequest("b1", "main", "merge me")
        )
        await gitlab.approve_merge_request(mr.ref)
        merged = await gitlab.merge_merge_request(mr.ref)
        assert merged.state is MRState.MERGED
        assert merged.merged_at is not None
        assert (await gitlab.read_file(project.id, _p("README.md"), "main")).content == "# merged\n"
        assert (await gitlab.get_merge_request(mr.ref)).state is MRState.MERGED

    async def test_after_a_merge_a_file_history_starts_with_the_branch_commit(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        """``git log -- <path>`` skips a merge whose path matches a parent's.

        So the history holds no merge commit, and the file's ``last_commit_id``
        names the commit that changed it; the fake once listed the merge commit
        first. The order is not checked: on a fast GitLab two commits made in
        the same second come back in either order (git sorts by commit date).
        """
        project = await new_project(FILES)
        await _branch_with_change(gitlab, project, "b1", "README.md", "# merged\n")
        change = (await gitlab.list_commits(project.id, ref="b1", path=_p("README.md")))[0]
        mr = await gitlab.create_merge_request(project.id, NewMergeRequest("b1", "main", "merge"))
        await gitlab.approve_merge_request(mr.ref)
        await gitlab.merge_merge_request(mr.ref)
        history = await gitlab.list_commits(project.id, ref="main", path=_p("README.md"))
        file = await gitlab.read_file(project.id, _p("README.md"), "main")
        assert file.last_commit_id == change.id
        assert change.id in {c.id for c in history}
        assert all(len(c.parent_ids) < 2 for c in history)

    async def test_merge_with_stale_sha_is_revision_conflict(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        await _branch_with_change(gitlab, project, "b1", "README.md", "# one\n")
        mr = await gitlab.create_merge_request(project.id, NewMergeRequest("b1", "main", "moving"))
        reviewed_sha = (await gitlab.get_merge_request(mr.ref)).sha
        await gitlab.commit(
            project.id,
            branch="b1",
            message="pushed after review",
            changes=[FileChange.update(_p("README.md"), "# two\n", last_commit_id=None)],
        )
        with pytest.raises(RevisionConflictError):
            await gitlab.merge_merge_request(mr.ref, sha=reviewed_sha)
        assert (
            await gitlab.read_file(project.id, _p("README.md"), "main")
        ).content == "# fixture\n"

    async def test_merge_of_the_new_head_right_after_a_push_succeeds(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        # GitLab updates an MR's sha in the background after a push; a merge naming the
        # branch's real head must still go through (CI and workflows push to MR branches).
        project = await new_project(FILES)
        await _branch_with_change(gitlab, project, "b1", "README.md", "# one\n")
        mr = await gitlab.create_merge_request(project.id, NewMergeRequest("b1", "main", "pushed"))
        pushed = await gitlab.commit(
            project.id,
            branch="b1",
            message="bot push [skip ci]",
            changes=[FileChange.update(_p("README.md"), "# two\n", last_commit_id=None)],
        )
        merged = await gitlab.merge_merge_request(mr.ref, sha=pushed.id)
        assert merged.state is MRState.MERGED
        assert (await gitlab.read_file(project.id, _p("README.md"), "main")).content == "# two\n"

    async def test_merge_with_conflicts_is_not_mergeable(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        await _branch_with_change(gitlab, project, "b1", "README.md", "# branch\n")
        mr = await gitlab.create_merge_request(
            project.id, NewMergeRequest("b1", "main", "conflict")
        )
        await gitlab.commit(
            project.id,
            branch="main",
            message="main moved",
            changes=[FileChange.update(_p("README.md"), "# main\n", last_commit_id=None)],
        )
        with pytest.raises(NotMergeableError):
            await gitlab.merge_merge_request(mr.ref)

    async def test_closed_mr_cannot_be_merged(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        await _branch_with_change(gitlab, project, "b1", "README.md", "# x\n")
        mr = await gitlab.create_merge_request(
            project.id, NewMergeRequest("b1", "main", "close me")
        )
        closed = await gitlab.close_merge_request(mr.ref)
        assert closed.state is MRState.CLOSED
        with pytest.raises(NotMergeableError):
            await gitlab.merge_merge_request(mr.ref)

    async def test_missing_merge_request_is_not_found(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        with pytest.raises(NotFoundError):
            await gitlab.get_merge_request(MergeRequestRef(project.id, 9999))

    # ── Projects ────────────────────────────────────────────────────────────

    async def test_get_project_by_id_and_by_path(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        assert (
            await gitlab.get_project(project.id)
        ).path_with_namespace == project.path_with_namespace
        assert (await gitlab.get_project(project.path_with_namespace)).id == project.id
        with pytest.raises(NotFoundError):
            await gitlab.get_project(f"{project.path_with_namespace}-missing")

    async def test_a_renamed_project_is_found_by_its_old_path(
        self, gitlab: GitLabPort, new_project: NewProject, rename_project: RenameProject
    ) -> None:
        project = await new_project(FILES)
        old = project.path_with_namespace
        await rename_project(project, f"{old.rsplit('/', 1)[-1]}-renamed")
        found = await gitlab.get_project(old)
        assert (found.id, found.path_with_namespace) == (project.id, f"{old}-renamed")
        assert found.web_url.endswith(f"/{old}-renamed")

    # ── Reading a repo at one commit (ADR-0035) ─────────────────────────────

    async def test_get_branch_gives_its_head_and_a_missing_one_is_not_found(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        head = await gitlab.get_branch(project.id, "main")
        assert head in await gitlab.list_branches(project.id)
        with pytest.raises(NotFoundError):
            await gitlab.get_branch(project.id, "no-such-branch")

    async def test_an_archive_holds_every_file_at_its_commit(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        head = await gitlab.get_branch(project.id, "main")
        await _branch_with_change(gitlab, project, "main", "README.md", "# later\n")
        archive = await gitlab.read_archive(project.id, head.commit_id, max_bytes=1_000_000)
        assert archive.commit_id == head.commit_id
        assert {path: content.decode() for path, content in archive.files.items()} == FILES

    async def test_an_archive_larger_than_allowed_is_refused(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        head = await gitlab.get_branch(project.id, "main")
        with pytest.raises(InvalidRequestError):
            await gitlab.read_archive(project.id, head.commit_id, max_bytes=8)

    async def test_any_commit_a_file_was_read_at_guards_its_update(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        project = await new_project(FILES)
        read_at = (await gitlab.get_branch(project.id, "main")).commit_id
        # Another file changes: README.md is still as it was at read_at.
        await _branch_with_change(gitlab, project, "main", "sites/site1/values.yaml", "a: 2\n")
        readme = _p("README.md")
        await gitlab.commit(
            project.id,
            branch="main",
            message="mine",
            changes=[FileChange.update(readme, "# mine\n", last_commit_id=read_at)],
        )
        # Now README.md changed after read_at.
        with pytest.raises(RevisionConflictError):
            await gitlab.commit(
                project.id,
                branch="main",
                message="mine again",
                changes=[FileChange.update(readme, "# again\n", last_commit_id=read_at)],
            )

    async def test_an_unknown_commit_as_the_guard_lets_the_write_through(
        self, gitlab: GitLabPort, new_project: NewProject
    ) -> None:
        # GitLab finds no "last change as of" an unknown commit, so it cannot
        # call the file changed. Wingman's own stale checks must not rely on it.
        project = await new_project(FILES)
        await gitlab.commit(
            project.id,
            branch="main",
            message="guarded by nothing GitLab knows",
            changes=[FileChange.update(_p("README.md"), "# x\n", last_commit_id="0" * 40)],
        )
        assert (await gitlab.read_file(project.id, _p("README.md"), "main")).content == "# x\n"
