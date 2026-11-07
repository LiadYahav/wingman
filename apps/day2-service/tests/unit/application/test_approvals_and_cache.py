"""Approvals by (team, iid), history, and the cache invalidation each write owes (ADR-0011)."""

from __future__ import annotations

import pytest

from wingman_core.application.approvals import SelfApprovalError, UnmanagedProjectError
from wingman_core.domain.errors import NotFoundError, RevisionConflictError
from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.domain.merge_request import MRState, NewMergeRequest
from wingman_core.domain.users import User
from wingman_core.infrastructure.cache import TtlCache
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day2.application.approvals import FileEdit
from wingman_day2.application.changes import ChangeResult, InstallSpec
from wingman_day2.application.services import Day2Services
from wingman_day2.domain.errors import ChangeRefusedError, UnknownTeamError
from wingman_day2.infrastructure import cache_keys

HERZI = "hosted:site1:prod:ocp4-prod-mce-site1-a:ocp4-prod-herzi-site1"
HERZI_DIR = "sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1"


async def install(services: Day2Services, user: User, team: str, chart: str) -> ChangeResult:
    return await services.changes.install(
        "ocp4-prod-hawk-site1" if team != "redbull" else HERZI, InstallSpec(team, chart), user
    )


# ── approvals ───────────────────────────────────────────────────────────────


async def test_pending_lists_wingman_mrs_of_every_team_with_the_real_requester(
    services: Day2Services, jane_user: User
) -> None:
    await install(services, jane_user, "redbull", "bmhgen")
    await install(services, jane_user, "lynx", "backup")
    pending = await services.approvals.pending()
    assert [(c.team.name, c.change.requested_by) for c in pending] == [
        ("lynx", "jane"),
        ("redbull", "jane"),
    ]


async def test_the_same_iid_in_two_teams_never_gets_confused(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User, bob_user: User
) -> None:
    redbull = await install(services, jane_user, "redbull", "bmhgen")
    lynx = await install(services, jane_user, "lynx", "backup")
    assert redbull.merge_request.ref.iid == lynx.merge_request.ref.iid == 1
    merged = await services.approvals.approve(
        "lynx", 1, sha=lynx.merge_request.sha, approver=bob_user
    )
    assert merged.state is MRState.MERGED
    still = await gitlab.get_merge_request(redbull.merge_request.ref)
    assert still.state is MRState.OPENED


async def test_nobody_approves_their_own_change_and_a_moved_branch_is_not_merged(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User, bob_user: User
) -> None:
    result = await install(services, jane_user, "redbull", "bmhgen")
    mr = result.merge_request
    with pytest.raises(SelfApprovalError):
        await services.approvals.approve("redbull", 1, sha=mr.sha, approver=jane_user)
    await gitlab.commit(
        mr.ref.project_id,
        branch=mr.source_branch,
        message="pushed after review",
        changes=[FileChange.create(RepoPath(f"{HERZI_DIR}/bmhgen/extra.yaml"), "x: 1\n")],
    )
    with pytest.raises(RevisionConflictError):
        await services.approvals.approve("redbull", 1, sha=mr.sha, approver=bob_user)


async def test_detail_edit_and_reject(
    services: Day2Services, gitlab: InMemoryGitLab, jane_user: User, bob_user: User
) -> None:
    await install(services, jane_user, "redbull", "bmhgen")
    change, diffs = await services.approvals.detail("redbull", 1)
    path = f"{HERZI_DIR}/bmhgen/values.yaml"
    assert [str(d.new_path) for d in diffs] == [path]
    assert change.change.title is not None
    with pytest.raises(ChangeRefusedError) as outside:
        await services.approvals.edit("redbull", 1, [FileEdit("README.md", "x")], "", bob_user)
    assert outside.value.details["rule"] == "path-not-in-mr"
    with pytest.raises(ChangeRefusedError):
        await services.approvals.edit("redbull", 1, [FileEdit("../x", "x")], "", bob_user)
    edited, _ = await services.approvals.edit(
        "redbull", 1, [FileEdit(path, "replicas: 5\n")], "tune", bob_user
    )
    branch = edited.change.merge_request.source_branch
    assert gitlab.snapshot(edited.change.merge_request.ref.project_id, branch)[path] == (
        "replicas: 5\n"
    )
    with pytest.raises(RevisionConflictError):
        await services.approvals.edit(
            "redbull", 1, [FileEdit(path, "replicas: 6\n", "0" * 40)], "", bob_user
        )
    closed = await services.approvals.reject("redbull", 1)
    assert closed.state is MRState.CLOSED
    with pytest.raises(ChangeRefusedError) as not_open:
        await services.approvals.edit("redbull", 1, [FileEdit(path, "a: 1\n")], "", bob_user)
    assert not_open.value.details["rule"] == "mr-not-open"


async def test_approvals_refuse_unknown_teams_and_non_wingman_mrs(
    services: Day2Services, gitlab: InMemoryGitLab
) -> None:
    with pytest.raises(UnknownTeamError):
        await services.approvals.detail("nope", 1)
    pid = (await gitlab.get_project("sigs/orca")).id
    await gitlab.commit(
        pid,
        branch="by-hand",
        start_branch="main",
        message="by hand",
        changes=[FileChange.create(RepoPath("x.yaml"), "a: 1\n")],
    )
    await gitlab.create_merge_request(pid, NewMergeRequest("by-hand", "main", "manual change"))
    with pytest.raises(UnmanagedProjectError):
        await services.approvals.detail("orca", 1)


# ── history ─────────────────────────────────────────────────────────────────


async def test_history_commits_mrs_and_diffs_across_teams(
    services: Day2Services, jane_user: User, bob_user: User
) -> None:
    result = await install(services, jane_user, "redbull", "bmhgen")
    await services.approvals.approve("redbull", 1, sha=result.merge_request.sha, approver=bob_user)
    commits = await services.audit.commits(per_page=50, page=1)
    assert {c.team for c in commits} == {"falcon", "lynx", "orca", "redbull"}
    assert commits == sorted(commits, key=lambda c: c.commit.authored_at, reverse=True)
    assert len(await services.audit.commits(per_page=2, page=2)) == 2
    mrs = await services.audit.merge_requests(per_page=10, page=1)
    assert [(m.team, m.merge_request.state) for m in mrs] == [("redbull", MRState.MERGED)]
    history = await services.audit.cluster_history("ocp4-prod-herzi-site1")
    # As `git log -- <path>`: the merge commit matches its branch parent, so the
    # newest entry is the commit that wrote the chart, not the merge.
    assert history[0].team == "redbull" and history[0].commit.title.startswith("Install bmhgen")
    team, diff = await services.audit.commit_diff(history[0].commit.id)
    assert team == "redbull" and [str(d.new_path) for d in diff] == [
        f"{HERZI_DIR}/bmhgen/values.yaml"
    ]
    with pytest.raises(NotFoundError):
        await services.audit.commit_diff("f" * 40, team="redbull")
    assert await services.audit.cluster_history("ocp4-upgrade-demo") == []


# ── cache invalidation: each fails if its write path stops invalidating ─────


async def test_opening_an_mr_shows_up_in_pending_immediately(
    services: Day2Services, jane_user: User
) -> None:
    assert await services.approvals.pending() == []  # now cached for the TTL
    await install(services, jane_user, "redbull", "bmhgen")
    assert len(await services.approvals.pending()) == 1


async def test_merging_shows_the_chart_as_installed_immediately(
    services: Day2Services, jane_user: User, bob_user: User
) -> None:
    result = await install(services, jane_user, "redbull", "bmhgen")
    before = await services.installed.for_cluster(HERZI)  # tree cached, MR not merged yet
    assert [c.app.chart for c in before.installed] == ["cluster-roles"]
    await services.approvals.approve("redbull", 1, sha=result.merge_request.sha, approver=bob_user)
    after = await services.installed.for_cluster(HERZI)
    assert [c.app.chart for c in after.installed] == ["bmhgen", "cluster-roles"]
    assert await services.approvals.pending() == []


async def test_rejecting_clears_the_pending_list(services: Day2Services, jane_user: User) -> None:
    await install(services, jane_user, "redbull", "bmhgen")
    assert len(await services.approvals.pending()) == 1
    await services.approvals.reject("redbull", 1)
    assert await services.approvals.pending() == []


async def test_writes_clear_exactly_the_project_they_changed(
    services: Day2Services, cache: TtlCache, gitlab: InMemoryGitLab, jane_user: User
) -> None:
    await services.topology.load()
    redbull = (await gitlab.get_project("sigs/redbull")).id
    lynx = (await gitlab.get_project("sigs/lynx")).id
    assert cache.invalidate_prefix(cache_keys.project_prefix(lynx)) > 0
    await services.topology.load()
    await install(services, jane_user, "redbull", "bmhgen")
    assert cache.invalidate_prefix(cache_keys.project_prefix(redbull)) == 0
    assert cache.invalidate_prefix(cache_keys.project_prefix(lynx)) > 0
