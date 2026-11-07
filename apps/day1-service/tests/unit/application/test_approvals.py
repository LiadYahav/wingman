"""Approvals over the day1 and specs projects: list, approve, reject, edit an MR's files."""

from __future__ import annotations

from typing import Any

import pytest

from wingman_core.application.approvals import SelfApprovalError
from wingman_core.domain.errors import RevisionConflictError
from wingman_core.domain.merge_request import MergeRequest, MRState
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_core.testing.fixtures import default_fixture_root, load_fixture_projects
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.approvals import RepoKey
from wingman_day1.application.clusters import CreateCluster
from wingman_day1.domain.errors import InvalidInputError, StaleError
from wingman_day1.domain.specs import validate_spec
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons

NEW = "ocp4-prod-falcon-site1"
NEW_PATH = f"sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/{NEW}.yaml"


def create_request(support: Any, name: str = NEW) -> CreateCluster:
    body = support.create_body(name)
    return CreateCluster(
        name=body["name"],
        site=body["site"],
        mce=body["mce"],
        spec_name=body["spec_name"],
        spec_version=body["spec_version"],
        variables=body["variables"],
    )


async def open_create(context: Day1Context, support: Any) -> MergeRequest:
    return (
        await context.clusters.create(create_request(support), user=support.ALICE)
    ).merge_request


async def test_pending_lists_open_wingman_mrs_of_both_projects_newest_first(
    context: Day1Context, support: Any
) -> None:
    cluster_mr = await open_create(context, support)
    spec = validate_spec({"metadata": {"name": "agent-mini", "version": "1"}})
    spec_mr = (await context.specs.create(spec, user=support.ALICE)).merge_request
    pending = await context.approvals.pending()
    assert [(c.repo, c.pending.merge_request.ref) for c in pending] == [
        (RepoKey.SPECS, spec_mr.ref),
        (RepoKey.DAY1, cluster_mr.ref),
    ]
    assert pending[0].pending.requested_by == "alice"


async def test_the_cached_list_reflects_every_write_at_once(
    context: Day1Context, support: Any
) -> None:
    # Legacy: writes cleared "approvals:day1:list" while the list was cached under
    # "approvals:combined:list", so new and decided MRs showed only after the TTL.
    assert await context.approvals.pending() == []
    cluster_mr = await open_create(context, support)
    assert [c.pending.merge_request.ref for c in await context.approvals.pending()] == [
        cluster_mr.ref
    ]
    spec = validate_spec({"metadata": {"name": "agent-mini", "version": "1"}})
    spec_mr = (await context.specs.create(spec, user=support.ALICE)).merge_request
    assert len(await context.approvals.pending()) == 2
    await context.approvals.approve(
        RepoKey.DAY1, cluster_mr.ref.iid, sha=cluster_mr.sha, approver=support.BOB
    )
    assert [c.repo for c in await context.approvals.pending()] == [RepoKey.SPECS]
    await context.approvals.reject(RepoKey.SPECS, spec_mr.ref.iid)
    assert await context.approvals.pending() == []


async def test_a_project_whose_default_branch_is_not_main_works(
    support: Any, hub: Any, identity: Any, clock: Any
) -> None:
    # Legacy: list_open_mrs hard-coded target_branch="main", so a repo whose default
    # branch is anything else never showed its MRs.
    gitlab = InMemoryGitLab(clock=clock)
    for fixture in load_fixture_projects(default_fixture_root()):
        if fixture.path_with_namespace in (support.DAY1, support.SPECS):
            gitlab.create_project(
                fixture.path_with_namespace, fixture.files, default_branch="production"
            )
    app = support.build_app(
        gitlab=gitlab, hub=hub, identity=identity, day2=FakeDay2Addons(), clock=clock
    )
    context: Day1Context = app.state.day1
    mr = await open_create(context, support)
    assert mr.target_branch == "production"
    assert [c.pending.merge_request.ref for c in await context.approvals.pending()] == [mr.ref]
    merged = await context.approvals.approve(
        RepoKey.DAY1, mr.ref.iid, sha=mr.sha, approver=support.BOB
    )
    assert merged.pending.merge_request.state is MRState.MERGED
    assert NEW in [c.ref.name for c in await context.clusters.clusters()]


async def test_the_requester_cannot_approve_their_own_change(
    context: Day1Context, support: Any
) -> None:
    mr = await open_create(context, support)
    with pytest.raises(SelfApprovalError):
        await context.approvals.approve(
            RepoKey.DAY1, mr.ref.iid, sha=mr.sha, approver=support.ALICE
        )


async def test_a_commit_pushed_after_review_is_not_merged_unseen(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    mr = await open_create(context, support)
    pid = await support.project_id(gitlab, support.DAY1)
    content = gitlab.snapshot(pid, mr.source_branch)[NEW_PATH]
    # The allocate-segment workflow commits vlanId onto the MR branch after the review.
    await support.push(
        gitlab,
        support.DAY1,
        branch=mr.source_branch,
        file=NEW_PATH,
        content=content + "vlanId: 412\n",
    )
    with pytest.raises(RevisionConflictError):
        await context.approvals.approve(RepoKey.DAY1, mr.ref.iid, sha=mr.sha, approver=support.BOB)
    assert NEW_PATH not in gitlab.snapshot(pid, "main")

    change, _ = await context.approvals.get(RepoKey.DAY1, mr.ref.iid)
    await context.approvals.approve(
        RepoKey.DAY1, mr.ref.iid, sha=change.pending.merge_request.sha, approver=support.BOB
    )
    assert "vlanId: 412" in gitlab.snapshot(pid, "main")[NEW_PATH]


async def test_reject_closes_without_merging(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    mr = await open_create(context, support)
    closed = await context.approvals.reject(RepoKey.DAY1, mr.ref.iid)
    assert closed.pending.merge_request.state is MRState.CLOSED
    pid = await support.project_id(gitlab, support.DAY1)
    assert NEW_PATH not in gitlab.snapshot(pid, "main")


async def test_get_returns_the_mr_and_its_diff(context: Day1Context, support: Any) -> None:
    mr = await open_create(context, support)
    change, diffs = await context.approvals.get(RepoKey.DAY1, mr.ref.iid)
    assert change.repo is RepoKey.DAY1
    assert [str(d.new_path) for d in diffs] == [NEW_PATH]
    assert diffs[0].new_file


async def test_an_edit_may_only_touch_files_the_mr_changes(
    context: Day1Context, support: Any
) -> None:
    mr = await open_create(context, support)
    with pytest.raises(InvalidInputError, match="only files this merge request changes"):
        await context.approvals.update(
            RepoKey.DAY1,
            mr.ref.iid,
            {"sites/configValues.yaml": "x: 1\n"},
            user=support.BOB,
        )


async def test_an_edit_of_a_cluster_file_keeps_what_automation_wrote(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    mr = await open_create(context, support)
    pid = await support.project_id(gitlab, support.DAY1)
    content = gitlab.snapshot(pid, mr.source_branch)[NEW_PATH] + "vlanId: 412\n"
    await support.push(
        gitlab, support.DAY1, branch=mr.source_branch, file=NEW_PATH, content=content
    )
    with pytest.raises(InvalidInputError) as caught:
        await context.approvals.update(
            RepoKey.DAY1,
            mr.ref.iid,
            {NEW_PATH: content.replace("vlanId: 412", "vlanId: 500")},
            user=support.BOB,
        )
    assert any("vlanId" in p for p in caught.value.problems)


async def test_an_edit_commits_on_top_of_the_branch_as_the_editor(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    mr = await open_create(context, support)
    pid = await support.project_id(gitlab, support.DAY1)
    content = gitlab.snapshot(pid, mr.source_branch)[NEW_PATH] + "vlanId: 412\n"
    await support.push(
        gitlab, support.DAY1, branch=mr.source_branch, file=NEW_PATH, content=content
    )
    head = (await context.approvals.get(RepoKey.DAY1, mr.ref.iid))[0].pending.merge_request.sha
    edited = content.replace("replicas: 2", "replicas: 3")
    change, _ = await context.approvals.update(
        RepoKey.DAY1, mr.ref.iid, {NEW_PATH: edited}, user=support.BOB, sha=head, message="more"
    )
    commits = await gitlab.list_commits(pid, ref=mr.source_branch, limit=3)
    assert [c.title for c in commits] == [
        "more",
        "outside push [skip ci]",
        f"Create cluster {NEW} from spec agent-standard",
    ]
    assert commits[0].author_name == "Bob Admin"
    assert commits[0].parent_ids == (head,)
    assert gitlab.snapshot(pid, mr.source_branch)[NEW_PATH] == edited
    assert change.pending.merge_request.sha == commits[0].id


async def test_an_edit_of_a_moved_branch_is_refused(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    mr = await open_create(context, support)
    pid = await support.project_id(gitlab, support.DAY1)
    content = gitlab.snapshot(pid, mr.source_branch)[NEW_PATH]
    await support.push(
        gitlab, support.DAY1, branch=mr.source_branch, file=NEW_PATH, content=content + "a: 1\n"
    )
    with pytest.raises(StaleError, match="moved since it was reviewed"):
        await context.approvals.update(
            RepoKey.DAY1, mr.ref.iid, {NEW_PATH: content}, user=support.BOB, sha=mr.sha
        )


async def test_an_edit_of_a_closed_mr_is_refused(context: Day1Context, support: Any) -> None:
    mr = await open_create(context, support)
    await context.approvals.reject(RepoKey.DAY1, mr.ref.iid)
    with pytest.raises(StaleError, match="only an open MR"):
        await context.approvals.update(RepoKey.DAY1, mr.ref.iid, {NEW_PATH: "x"}, user=support.BOB)


async def test_an_edit_of_a_spec_file_must_stay_a_valid_spec(
    context: Day1Context, support: Any
) -> None:
    spec = validate_spec({"metadata": {"name": "agent-mini", "version": "1"}})
    mr = (await context.specs.create(spec, user=support.ALICE)).merge_request
    with pytest.raises(InvalidInputError):
        await context.approvals.update(
            RepoKey.SPECS,
            mr.ref.iid,
            {"specs/agent-mini.yaml": "metadata: {name: other, version: '1'}\n"},
            user=support.BOB,
        )
    change, diffs = await context.approvals.update(
        RepoKey.SPECS,
        mr.ref.iid,
        {"specs/agent-mini.yaml": "metadata: {name: agent-mini, version: '2'}\n"},
        user=support.BOB,
    )
    assert change.repo is RepoKey.SPECS
    assert "version: '2'" in diffs[0].diff
