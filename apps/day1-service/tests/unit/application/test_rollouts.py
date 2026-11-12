"""A flavor's changes reach each cluster through its own MR (ADR-0044), on the in-memory GitLab.

The fixture clusters are linked to ``agent-baseline`` v1.0.0 by a header on
main, as a merged import leaves them; a new version is pushed to the specs
repo's main, as a merged flavor MR leaves it. ``lark`` needs configs changed
(removals, rolling nodes), ``heron`` needs a person (no network config),
``herzi`` and ``karniol`` have no nodepool (only the header moves); day2
reports ``cluster-roles`` installed on ``herzi`` only.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi import FastAPI

from wingman_core.domain.errors import AmbiguousWriteError, GitUnavailableError
from wingman_core.domain.git import RepoPath
from wingman_core.domain.merge_request import MergeRequest, MRState, NewMergeRequest
from wingman_core.domain.mr_conventions import parse_mr_description, rollout_branch
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.approvals import RepoKey
from wingman_day1.application.drift import DriftState
from wingman_day1.application.rollouts import RolloutState, RolloutStatus
from wingman_day1.domain.errors import AlreadyInUseError, InvalidSpecError
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.domain.rollout import RolloutTrigger
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons

MCE = "ocp4-prod-mce-site1-a"
LARK = ClusterRef("site1", MCE, "ocp4-prod-lark-site1")
HERON = ClusterRef("site1", MCE, "ocp4-prod-heron-site1")
HERZI = ClusterRef("site1", MCE, "ocp4-prod-herzi-site1")
KARNIOL = ClusterRef("site1", MCE, "ocp4-prod-karniol-site1")
FLAVOR = "agent-baseline"
SPEC_FILE = "specs/agent-baseline.yaml"


def header(version: str | None, flavor: str = FLAVOR) -> str:
    line = f'# specName: "{flavor}"\n'
    return line + (f'# specVersion: "{version}"\n' if version is not None else "")


async def link(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab, ref: ClusterRef, version: str | None
) -> None:
    """The cluster's file on main with the flavor's header, as a merged import leaves it."""
    pid = await support.project_id(gitlab, support.DAY1)
    before = (await gitlab.read_file(pid, ref.path, "main")).content
    await support.push(
        gitlab, support.DAY1, branch="main", file=str(ref.path), content=header(version) + before
    )
    context.repos[RepoKey.DAY1].forget_files()


async def release(
    context: Day1Context,
    support: Any,
    gitlab: InMemoryGitLab,
    version: str,
    *,
    adds: tuple[str, ...] = (),
) -> None:
    """A new version of the flavor on the specs repo's main, as its merged MR leaves it."""
    pid = await support.project_id(gitlab, support.SPECS)
    current = (await gitlab.read_file(pid, RepoPath(SPEC_FILE), "main")).content
    text = re.sub(r'version: "[^"]+"', f'version: "{version}"', current, count=1)
    for name in adds:
        text += f"      - team: redbull\n        name: {name}\n        version: main\n"
        text += "        overrideable: []\n"
    await support.push(gitlab, support.SPECS, branch="main", file=SPEC_FILE, content=text)
    context.repos[RepoKey.SPECS].forget_files()


async def rollout_mrs(
    gitlab: InMemoryGitLab, support: Any, *, state: MRState | None = MRState.OPENED
) -> dict[str, MergeRequest]:
    """The day1 rollout MRs, by the cluster their branch names."""
    pid = await support.project_id(gitlab, support.DAY1)
    found = await gitlab.list_merge_requests(pid, state=state, labels=("rollout",))
    return {mr.source_branch.rsplit("/", 1)[1]: mr for mr in found}


def states(status: RolloutStatus) -> dict[str, RolloutState]:
    return {c.cluster.ref.name: c.state for c in status.clusters}


def counted(app: FastAPI, metric: str, **labels: str) -> float | None:
    return app.state.metrics.registry.get_sample_value(metric, labels)


# ── A cluster is measured against its own version ────────────────────────────


async def test_a_cluster_is_measured_against_the_version_its_header_names(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, HERZI, "1.0.0")
    assert (await context.drift.for_cluster(HERZI)).state is DriftState.IN_SYNC
    await release(context, support, gitlab, "1.1.0", adds=("bmhgen",))
    drift = await context.drift.for_cluster(HERZI)
    # v1.0.0 does not list bmhgen: the newer version is an update, never drift
    assert (drift.state, drift.addon_drift, drift.value_drift) == (DriftState.IN_SYNC, (), ())
    assert (drift.spec_version, drift.current_spec_version) == ("1.0.0", "1.1.0")
    assert drift.update is not None
    assert (drift.update.version, drift.update.merge_request) == ("1.1.0", None)


async def test_an_older_version_is_read_from_the_specs_history(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await release(context, support, gitlab, "1.1.0", adds=("bmhgen",))
    await release(context, support, gitlab, "1.2.0", adds=("kyverno",))
    await link(context, support, gitlab, HERZI, "1.1.0")
    drift = await context.drift.for_cluster(HERZI)
    # Missing add-ons per the cluster's own version: bmhgen, not v1.2.0's kyverno
    assert drift.state is DriftState.DRIFTED
    assert [a.name for a in drift.addon_drift] == ["bmhgen"]
    assert drift.update is not None and drift.update.version == "1.2.0"
    again = await context.specs.at_version(FLAVOR, "1.1.0")
    assert again is not None and again is await context.specs.at_version(FLAVOR, "1.1.0")


async def test_a_version_the_history_does_not_have_is_unknown_never_in_sync(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, HERZI, "0.9.0")
    drift = await context.drift.for_cluster(HERZI)
    assert drift.state is DriftState.UNKNOWN
    assert drift.error == "flavor 'agent-baseline' v0.9.0 is not in the specs repo's history"
    assert drift.update is not None and drift.update.version == "1.0.0"


async def test_a_header_without_a_version_is_unknown(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, HERZI, None)
    drift = await context.drift.for_cluster(HERZI)
    assert drift.state is DriftState.UNKNOWN
    assert drift.error is not None and drift.error.startswith("the header names no version")


async def test_a_flavor_edit_needs_a_version_never_saved_before(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    spec = await context.specs.get(FLAVOR)
    with pytest.raises(InvalidSpecError) as caught:
        await context.specs.update(FLAVOR, spec, user=support.ALICE)
    assert caught.value.problems == (
        "metadata.version: 1.0.0 is the current version; an edit needs a new one, which "
        "reaches each cluster through its own merge request",
    )
    await release(context, support, gitlab, "1.1.0")
    with pytest.raises(InvalidSpecError) as caught:
        await context.specs.update(FLAVOR, spec, user=support.ALICE)  # spec is v1.0.0
    assert caught.value.problems == (
        "metadata.version: 1.0.0 was used before; a version never changes once saved",
    )
    newer = spec.model_copy(
        update={"metadata": spec.metadata.model_copy(update={"version": "1.2.0"})}
    )
    result = await context.specs.update(FLAVOR, newer, user=support.ALICE)
    assert result.merge_request.title == "[Wingman/Specs] Update spec agent-baseline to v1.2.0"


# ── A new version opens one MR per cluster ───────────────────────────────────


async def test_a_new_version_opens_one_mr_per_cluster_each_on_its_own_branch(
    app: FastAPI, context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    for ref in (LARK, HERON, HERZI, KARNIOL):
        await link(context, support, gitlab, ref, "1.0.0")
    await release(context, support, gitlab, "1.1.0")
    pid = await support.project_id(gitlab, support.DAY1)
    main = gitlab.snapshot(pid, "main")

    run = await context.rollouts.run(FLAVOR, RolloutTrigger.MERGE)
    assert (run.version, run.opened, run.failed) == ("1.1.0", 3, 0)
    opened = await rollout_mrs(gitlab, support)
    assert sorted(opened) == sorted([LARK.name, HERZI.name, KARNIOL.name])
    for ref in (LARK, HERZI, KARNIOL):
        mr = opened[ref.name]
        assert mr.source_branch == rollout_branch(flavor=FLAVOR, version="1.1.0", cluster=ref.name)
        assert mr.title == f"[Wingman/Day1] Sync cluster {ref.name} to spec agent-baseline v1.1.0"
        assert set(mr.labels) == {"wingman", "day1", "sync", "rollout"}
        footer = parse_mr_description(mr.description)
        assert footer is not None and footer.author == "system:wingman-rollout"
        assert mr.description.startswith(
            "**Rollout of flavor `agent-baseline` v1.1.0** to this cluster, which is on v1.0.0."
        )
        branch = gitlab.snapshot(pid, mr.source_branch)
        # Its own file only, and its header now names v1.1.0
        assert [p for p in branch if branch[p] != main.get(p)] == [str(ref.path)]
        assert branch[str(ref.path)].startswith(header("1.1.0"))
    # LARK's MR says what it removes and that its nodes roll, as the approve page did
    assert "**This removes machine configs:**" in opened[LARK.name].description
    assert "**Merging rolls nodes.**" in opened[LARK.name].description

    status = await context.rollouts.status(FLAVOR)
    assert states(status) == {
        LARK.name: RolloutState.MERGE_REQUEST_OPEN,
        HERON.name: RolloutState.NEEDS_DECISION,
        HERZI.name: RolloutState.MERGE_REQUEST_OPEN,
        KARNIOL.name: RolloutState.MERGE_REQUEST_OPEN,
    }
    (heron,) = [c for c in status.clusters if c.cluster.ref == HERON]
    assert heron.merge_request is None
    assert heron.reasons[0].startswith("nodepool[0].configs: nodepool[0] has no network config")
    labels = {"outcome": "opened"}
    assert counted(app, "wingman_rollout_merge_requests_total", **labels) == 3
    assert counted(app, "wingman_rollout_runs_total", trigger="merge") == 1
    # The cluster's drift now points at its update MR
    drift = await context.drift.for_cluster(HERZI)
    assert drift.update is not None and drift.update.merge_request is not None
    assert drift.update.merge_request.ref == opened[HERZI.name].ref


async def test_a_second_run_or_a_new_replica_finds_what_is_open_and_opens_nothing(
    context: Day1Context,
    support: Any,
    gitlab: InMemoryGitLab,
    day2: FakeDay2Addons,
    clock: Any,
) -> None:
    await link(context, support, gitlab, HERZI, "1.0.0")
    await link(context, support, gitlab, KARNIOL, "1.0.0")
    await release(context, support, gitlab, "1.1.0")
    assert (await context.rollouts.run(FLAVOR, RolloutTrigger.MERGE)).opened == 2
    assert (await context.rollouts.run(FLAVOR, RolloutTrigger.WEBHOOK)).opened == 0
    # A replica that just started knows nothing but what GitLab holds
    replica = support.build_app(gitlab=gitlab, hub=None, identity=None, day2=day2, clock=clock)
    other: Day1Context = replica.state.day1
    assert (await other.rollouts.run(FLAVOR, RolloutTrigger.READ)).opened == 0
    assert len(await rollout_mrs(gitlab, support)) == 2


async def test_an_unconfirmed_merge_request_is_checked_by_its_branch_not_sent_again(
    app: FastAPI,
    context: Day1Context,
    support: Any,
    gitlab: InMemoryGitLab,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await link(context, support, gitlab, LARK, "1.0.0")
    await release(context, support, gitlab, "1.1.0")
    pid = await support.project_id(gitlab, support.DAY1)
    real_create = gitlab.create_merge_request

    async def times_out(project_id: int, request: NewMergeRequest) -> MergeRequest:
        # The commit landed on its branch; GitLab never confirmed the MR.
        raise AmbiguousWriteError("POST /merge_requests timed out after it was sent")

    monkeypatch.setattr(gitlab, "create_merge_request", times_out)
    run = await context.rollouts.run(FLAVOR, RolloutTrigger.MERGE)
    assert (run.opened, run.failed) == (0, 1)
    (lark,) = (await context.rollouts.status(FLAVOR)).clusters
    assert lark.state is RolloutState.FAILED
    assert lark.reasons[0].startswith("GitLab did not confirm the merge request")
    branch = rollout_branch(flavor=FLAVOR, version="1.1.0", cluster=LARK.name)
    commits = await gitlab.list_commits(pid, ref=branch, limit=3)

    monkeypatch.setattr(gitlab, "create_merge_request", real_create)
    # A read-triggered run waits RETRY_AFTER; an admin's Reconcile does not
    assert (await context.rollouts.run(FLAVOR, RolloutTrigger.READ)).opened == 0
    run = await context.rollouts.run(FLAVOR, RolloutTrigger.RECONCILE, force=True)
    assert run.opened == 1
    # The branch kept its one commit: only the MR was sent the second time
    assert await gitlab.list_commits(pid, ref=branch, limit=3) == commits
    assert list(await rollout_mrs(gitlab, support)) == [LARK.name]
    outcome = "wingman_rollout_merge_requests_total"
    assert counted(app, outcome, outcome="unconfirmed") == 1
    assert counted(app, outcome, outcome="recovered") == 1


async def test_once_gitlab_stops_answering_a_run_starts_no_more_mrs(
    app: FastAPI,
    context: Day1Context,
    support: Any,
    gitlab: InMemoryGitLab,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for ref in (HERZI, KARNIOL):
        await link(context, support, gitlab, ref, "1.0.0")
    await release(context, support, gitlab, "1.1.0")
    sent: list[str] = []

    async def down(project_id: int, **kwargs: Any) -> Any:
        sent.append(kwargs["branch"])
        raise GitUnavailableError("connection refused")

    monkeypatch.setattr(gitlab, "commit", down)
    run = await context.rollouts.run(FLAVOR, RolloutTrigger.MERGE)
    assert (run.opened, run.failed) == (0, 2)
    assert len(sent) == 1
    reasons = sorted(c.reasons[0] for c in (await context.rollouts.status(FLAVOR)).clusters)
    assert reasons[0] == "GitUnavailableError: connection refused"
    assert reasons[1].startswith("not sent: GitLab did not answer for ocp4-prod-")
    assert counted(app, "wingman_rollout_merge_requests_total", outcome="not_sent") == 1


async def test_a_newer_version_supersedes_the_open_mr_of_an_older_one(
    app: FastAPI, context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, HERZI, "1.0.0")
    await release(context, support, gitlab, "1.1.0")
    await context.rollouts.run(FLAVOR, RolloutTrigger.MERGE)
    old = (await rollout_mrs(gitlab, support))[HERZI.name]
    await release(context, support, gitlab, "1.2.0")
    await context.rollouts.run(FLAVOR, RolloutTrigger.MERGE)
    new = (await rollout_mrs(gitlab, support))[HERZI.name]
    assert new.title.endswith("to spec agent-baseline v1.2.0")
    closed = await gitlab.get_merge_request(old.ref)
    assert closed.state is MRState.CLOSED
    (note,) = gitlab.notes(old.ref)
    assert note.startswith(f"Superseded by !{new.ref.iid} ({new.web_url})")
    assert counted(app, "wingman_rollout_merge_requests_total", outcome="superseded") == 1
    # A superseded MR is not a decline: the cluster's state is its new MR
    assert states(await context.rollouts.status(FLAVOR)) == {
        HERZI.name: RolloutState.MERGE_REQUEST_OPEN
    }


async def test_a_closed_rollout_mr_declines_that_version_and_is_not_reopened(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, HERZI, "1.0.0")
    await release(context, support, gitlab, "1.1.0")
    await context.rollouts.run(FLAVOR, RolloutTrigger.MERGE)
    mr = (await rollout_mrs(gitlab, support))[HERZI.name]
    await context.approvals.reject(RepoKey.DAY1, mr.ref.iid)
    assert (await context.rollouts.run(FLAVOR, RolloutTrigger.RECONCILE, force=True)).opened == 0
    (herzi,) = (await context.rollouts.status(FLAVOR)).clusters
    assert herzi.state is RolloutState.DECLINED
    assert herzi.merge_request is not None and herzi.merge_request.ref == mr.ref


async def test_merged_mrs_leave_the_cluster_on_the_version_and_its_add_ons_against_it(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, HERZI, "1.0.0")
    await release(context, support, gitlab, "1.1.0", adds=("bmhgen",))
    await context.rollouts.run(FLAVOR, RolloutTrigger.MERGE)
    mr = (await rollout_mrs(gitlab, support))[HERZI.name]
    await context.approvals.approve(RepoKey.DAY1, mr.ref.iid, sha=mr.sha, approver=support.BOB)
    status = await context.rollouts.status(FLAVOR)
    assert states(status) == {HERZI.name: RolloutState.ON_VERSION}
    drift = await context.drift.for_cluster(HERZI)
    # Now on v1.1.0, which lists bmhgen: missing until day2's MR merges
    assert (drift.spec_version, drift.update) == ("1.1.0", None)
    assert [a.name for a in drift.addon_drift] == ["bmhgen"]


async def test_the_add_ons_a_version_needs_are_asked_of_day2_once_and_linked(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab, day2: FakeDay2Addons
) -> None:
    await link(context, support, gitlab, HERZI, "1.0.0")
    await link(context, support, gitlab, KARNIOL, "1.0.0")
    await release(context, support, gitlab, "1.1.0", adds=("bmhgen",))
    await context.rollouts.run(FLAVOR, RolloutTrigger.MERGE)
    asked = {ref.name: [a.name for a in addons] for ref, addons, _ in day2.install_requests}
    # Missing per v1.1.0: herzi has cluster-roles already, karniol has nothing
    assert asked == {HERZI.name: ["bmhgen"], KARNIOL.name: ["cluster-roles", "bmhgen"]}
    opened = await rollout_mrs(gitlab, support)
    (karniol_install,) = [mr for name, mr in day2.open_merge_requests if name == KARNIOL.name]
    assert f"- redbull !{karniol_install.iid}: {karniol_install.title}" in (
        opened[KARNIOL.name].description
    )
    assert "merge them with this one" in opened[KARNIOL.name].description
    await context.rollouts.run(FLAVOR, RolloutTrigger.RECONCILE, force=True)
    assert len(day2.install_requests) == 2  # their MRs are open: not asked again


async def test_a_team_day2_refuses_is_listed_in_the_day1_mr_which_still_opens(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab, day2: FakeDay2Addons
) -> None:
    await link(context, support, gitlab, HERZI, "1.0.0")
    day2.refuse = {"redbull": "redbull hasn't given Wingman write access to sigs/redbull"}
    await release(context, support, gitlab, "1.1.0", adds=("bmhgen",))
    await context.rollouts.run(FLAVOR, RolloutTrigger.MERGE)
    description = (await rollout_mrs(gitlab, support))[HERZI.name].description
    assert "Not opened in day2 (install them from the cluster's Add-ons tab):" in description
    assert "- redbull: redbull hasn't given Wingman write access to sigs/redbull" in description


async def test_reading_the_status_with_work_pending_starts_a_run(
    app: FastAPI, context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, HERZI, "1.0.0")
    await release(context, support, gitlab, "1.1.0")
    status = await context.rollouts.read(FLAVOR)
    assert status.running
    assert states(status) == {HERZI.name: RolloutState.PENDING}
    await context.rollouts.wait(FLAVOR)
    status = await context.rollouts.read(FLAVOR)
    assert not status.running
    assert states(status) == {HERZI.name: RolloutState.MERGE_REQUEST_OPEN}
    assert status.last_run is not None
    assert (status.last_run.trigger, status.last_run.opened) == (RolloutTrigger.READ, 1)
    assert counted(app, "wingman_rollout_runs_total", trigger="read") == 1


async def test_what_merging_a_new_version_opens_is_known_before_the_merge(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    for ref in (LARK, HERON, HERZI):
        await link(context, support, gitlab, ref, "1.0.0")
    spec = await context.specs.get(FLAVOR)
    newer = spec.model_copy(
        update={"metadata": spec.metadata.model_copy(update={"version": "1.1.0"})}
    )
    preview = await context.rollouts.preview(FLAVOR, newer)
    assert (preview.following, preview.opens, preview.already_on_version) == (3, 2, 0)
    assert [d.ref for d in preview.needs_decision] == [HERON]
    assert [r.ref for r in preview.rolls_nodes] == [LARK]
    assert [r.ref for r in preview.removes_configs] == [LARK]
    assert [(r.nodepool.index, r.name) for r in preview.removes_configs[0].removals] == [
        (0, "worker-kubeletconfig-reserved"),
        (1, "restored-example-config"),
    ]
    assert (preview.version, preview.current_version, preview.adds_addons) == ("1.1.0", "1.0.0", ())
    # Nothing was opened
    assert await rollout_mrs(gitlab, support, state=None) == {}


# ── A sync by hand ───────────────────────────────────────────────────────────


async def test_a_sync_is_refused_while_an_mr_already_takes_the_cluster_to_the_version(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, HERZI, "1.0.0")
    await release(context, support, gitlab, "1.1.0")
    await context.rollouts.run(FLAVOR, RolloutTrigger.MERGE)
    plan = await context.sync.preview(HERZI, hardware={})
    with pytest.raises(AlreadyInUseError, match="an open merge request already syncs"):
        await context.sync.sync(
            HERZI,
            last_commit_id=plan.cluster.last_commit_id,
            spec_version="1.1.0",
            hardware={},
            confirm_removals=[],
            user=support.ALICE,
        )


async def test_a_sync_by_hand_supersedes_an_open_mr_to_an_older_version(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await link(context, support, gitlab, HERZI, "1.0.0")
    await release(context, support, gitlab, "1.1.0")
    await context.rollouts.run(FLAVOR, RolloutTrigger.MERGE)
    old = (await rollout_mrs(gitlab, support))[HERZI.name]
    await release(context, support, gitlab, "1.2.0")
    plan = await context.sync.preview(HERZI, hardware={})
    result = await context.sync.sync(
        HERZI,
        last_commit_id=plan.cluster.last_commit_id,
        spec_version="1.2.0",
        hardware={},
        confirm_removals=[],
        user=support.ALICE,
    )
    assert (await gitlab.get_merge_request(old.ref)).state is MRState.CLOSED
    (note,) = gitlab.notes(old.ref)
    assert f"Superseded by !{result.provision.merge_request.ref.iid}" in note
