"""The approval flow against the in-memory GitLab."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from wingman_core.application.approvals import (
    Approvals,
    SelfApprovalError,
    UnmanagedProjectError,
)
from wingman_core.domain.errors import RevisionConflictError
from wingman_core.domain.git import FileChange, Project, RepoPath
from wingman_core.domain.merge_request import (
    MergeRequest,
    MergeRequestRef,
    MRState,
    NewMergeRequest,
)
from wingman_core.domain.mr_conventions import (
    WINGMAN_LABEL,
    MRMetadata,
    Repo,
    ResourceType,
    Verb,
    mr_description,
    mr_title,
)
from wingman_core.domain.users import Role, User
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab

JANE = User("jane", Role.ADMIN)
BOB = User("bob", Role.ADMIN)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 7, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


async def open_change(
    gitlab: InMemoryGitLab,
    project: Project,
    *,
    branch: str,
    requester: str,
    labels: tuple[str, ...],
) -> MergeRequest:
    await gitlab.commit(
        project.id,
        branch=branch,
        start_branch="main",
        message=f"change {branch}",
        changes=[FileChange.create(RepoPath(f"{branch}.yaml"), "x: 1\n")],
    )
    metadata = MRMetadata(requester, "create", ResourceType.CLUSTER, branch, Repo.DAY1)
    return await gitlab.create_merge_request(
        project.id,
        NewMergeRequest(
            branch,
            "main",
            mr_title(Repo.DAY1, Verb.CREATE, ResourceType.CLUSTER, branch),
            mr_description("why", metadata),
            labels=labels,
        ),
    )


@pytest.fixture
def gitlab() -> InMemoryGitLab:
    return InMemoryGitLab(clock=Clock())


async def test_get_reads_the_requester_and_title_of_a_wingman_mr(
    gitlab: InMemoryGitLab,
) -> None:
    team = gitlab.create_project("sigs/b", {"README.md": "b"})
    mr = await open_change(gitlab, team, branch="two", requester="bob", labels=(WINGMAN_LABEL,))
    change = await Approvals(gitlab).get(mr.ref, managed={team.id})
    assert change.requested_by == "bob"
    assert change.title is not None and change.title.resource_name == "two"


class LaggingGitLab(InMemoryGitLab):
    """GitLab before its background job has caught up: an MR's ``sha`` is ``stale``."""

    stale: str | None = None

    async def get_merge_request(self, ref: MergeRequestRef) -> MergeRequest:
        merge_request = await super().get_merge_request(ref)
        return dataclasses.replace(merge_request, sha=self.stale) if self.stale else merge_request


async def test_an_open_mr_is_read_at_its_branch_head_while_gitlab_lags() -> None:
    gitlab = LaggingGitLab(clock=Clock())
    team = gitlab.create_project("sigs/b", {"README.md": "b"})
    mr = await open_change(gitlab, team, branch="two", requester="bob", labels=(WINGMAN_LABEL,))
    pushed = await gitlab.commit(
        team.id,
        branch="two",
        message="a bot pushes after the MR was opened",
        changes=[FileChange.create(RepoPath("more.yaml"), "y: 1\n")],
    )
    gitlab.stale = mr.sha
    change = await Approvals(gitlab).get(mr.ref, managed={team.id})
    assert change.merge_request.sha == pushed.id != mr.sha
    # Once merged or closed there is no branch to read: the MR is as GitLab says.
    await gitlab.close_merge_request(mr.ref)
    closed = await Approvals(gitlab).get(mr.ref, managed={team.id})
    assert closed.merge_request.sha == mr.sha


async def test_get_refuses_an_mr_without_the_wingman_label(gitlab: InMemoryGitLab) -> None:
    team = gitlab.create_project("sigs/b", {"README.md": "b"})
    mr = await open_change(gitlab, team, branch="manual", requester="x", labels=("other",))
    with pytest.raises(UnmanagedProjectError, match="not a Wingman merge request"):
        await Approvals(gitlab).get(mr.ref, managed={team.id})


async def test_same_number_in_two_projects_acts_on_the_right_one(gitlab: InMemoryGitLab) -> None:
    team_a = gitlab.create_project("sigs/a", {"README.md": "a"})
    team_b = gitlab.create_project("sigs/b", {"README.md": "b"})
    mr_a = await open_change(
        gitlab, team_a, branch="one", requester="jane", labels=(WINGMAN_LABEL,)
    )
    mr_b = await open_change(
        gitlab, team_b, branch="one", requester="jane", labels=(WINGMAN_LABEL,)
    )
    assert mr_a.ref.iid == mr_b.ref.iid
    merged = await Approvals(gitlab).approve(
        mr_b.ref, approver=BOB, reviewed_sha=mr_b.sha, managed={team_a.id, team_b.id}
    )
    assert merged.state is MRState.MERGED
    assert (await gitlab.get_merge_request(mr_a.ref)).state is MRState.OPENED
    assert "one.yaml" in gitlab.snapshot(team_b.id, "main")
    assert "one.yaml" not in gitlab.snapshot(team_a.id, "main")


async def test_nobody_approves_their_own_change(gitlab: InMemoryGitLab) -> None:
    project = gitlab.create_project("g/p", {"README.md": "a"})
    mr = await open_change(
        gitlab, project, branch="mine", requester="jane", labels=(WINGMAN_LABEL,)
    )
    with pytest.raises(SelfApprovalError):
        await Approvals(gitlab).approve(
            mr.ref, approver=JANE, reviewed_sha=mr.sha, managed={project.id}
        )
    assert (await gitlab.get_merge_request(mr.ref)).state is MRState.OPENED


async def test_commits_pushed_after_review_are_not_merged_unseen(gitlab: InMemoryGitLab) -> None:
    project = gitlab.create_project("g/p", {"README.md": "a"})
    mr = await open_change(gitlab, project, branch="b", requester="jane", labels=(WINGMAN_LABEL,))
    reviewed = mr.sha
    await gitlab.commit(
        project.id,
        branch="b",
        message="ci: allocate segment",
        changes=[
            FileChange.update(RepoPath("b.yaml"), "x: 1\nvlanId: 1011\n", last_commit_id=None)
        ],
    )
    with pytest.raises(RevisionConflictError):
        await Approvals(gitlab).approve(
            mr.ref, approver=BOB, reviewed_sha=reviewed, managed={project.id}
        )


async def test_only_managed_wingman_mrs_can_be_acted_on(gitlab: InMemoryGitLab) -> None:
    project = gitlab.create_project("g/p", {"README.md": "a"})
    manual = await open_change(gitlab, project, branch="m", requester="x", labels=("other",))
    approvals = Approvals(gitlab)
    with pytest.raises(UnmanagedProjectError):
        await approvals.reject(manual.ref, managed={project.id + 100})
    with pytest.raises(UnmanagedProjectError):
        await approvals.reject(manual.ref, managed={project.id})


async def test_reject_closes(gitlab: InMemoryGitLab) -> None:
    project = gitlab.create_project("g/p", {"README.md": "a"})
    mr = await open_change(gitlab, project, branch="b", requester="jane", labels=(WINGMAN_LABEL,))
    closed = await Approvals(gitlab).reject(mr.ref, managed={project.id})
    assert closed.state is MRState.CLOSED


async def test_a_change_without_a_footer_is_attributed_to_the_gitlab_author(
    gitlab: InMemoryGitLab,
) -> None:
    project = gitlab.create_project("g/p", {"README.md": "a"})
    await gitlab.commit(
        project.id,
        branch="raw",
        start_branch="main",
        message="m",
        changes=[FileChange.create(RepoPath("raw.yaml"), "x")],
    )
    mr = await gitlab.create_merge_request(
        project.id, NewMergeRequest("raw", "main", "Hand-made", labels=(WINGMAN_LABEL,))
    )
    change = await Approvals(gitlab).get(mr.ref, managed={project.id})
    assert (change.requested_by, change.metadata, change.title) == ("wingman-bot", None, None)
