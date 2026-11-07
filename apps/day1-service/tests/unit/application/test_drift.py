"""Drift: spec addons against what day2 reports; unknown is never "in sync"."""

from __future__ import annotations

from typing import Any

from wingman_core.domain.git import FileChange, RepoPath
from wingman_core.infrastructure.fake_gitlab import InMemoryGitLab
from wingman_day1.api.deps import Day1Context
from wingman_day1.application.approvals import RepoKey
from wingman_day1.application.clusters import CreateCluster
from wingman_day1.application.drift import DriftState
from wingman_day1.domain.addons import AddonDriftReason, InstalledAddon
from wingman_day1.domain.paths import ClusterRef
from wingman_day1.infrastructure.fake_day2 import FakeDay2Addons

NEW = "ocp4-prod-falcon-site1"
REF = ClusterRef("site1", "ocp4-prod-mce-site1-a", NEW)


async def create_merged(
    context: Day1Context,
    support: Any,
    *,
    spec_name: str = "agent-standard",
    overrides: dict[str, dict[str, object]] | None = None,
) -> None:
    body = support.create_body()
    variables = dict(body["variables"])
    if spec_name == "agent-single":
        variables["nodepools"] = support.nodepools("dell-r660-site1-128c-1024gb-5tb")
    result = await context.clusters.create(
        CreateCluster(
            name=NEW,
            site=body["site"],
            mce=body["mce"],
            spec_name=spec_name,
            spec_version="1.0.0",
            variables=variables,
            addon_overrides=overrides or {},
        ),
        user=support.ALICE,
    )
    await context.approvals.approve(
        RepoKey.DAY1,
        result.merge_request.ref.iid,
        sha=result.merge_request.sha,
        approver=support.BOB,
    )


async def test_clusters_without_a_spec_header_are_not_linked(context: Day1Context) -> None:
    summary = await context.drift.summary()
    assert len(summary) == 12
    assert {d.state for d in summary} == {DriftState.NOT_LINKED}
    assert all(d.is_drifted is False for d in summary)


async def test_a_missing_spec_addon_is_drift_and_carries_the_requested_values(
    context: Day1Context, support: Any
) -> None:
    # Legacy: overrides were dropped at create, so "Fix" installed the addon with {}.
    await create_merged(context, support, overrides={"redbull/cluster-roles": {"a": 1}})
    drift = await context.drift.for_cluster(REF)
    assert drift.state is DriftState.DRIFTED
    assert drift.is_drifted is True
    [missing] = drift.addon_drift
    assert (missing.team, missing.name, missing.reason) == (
        "redbull",
        "cluster-roles",
        AddonDriftReason.MISSING,
    )
    assert missing.override_values == {"a": 1}
    assert (drift.spec_name, drift.spec_version, drift.current_spec_version) == (
        "agent-standard",
        "1.0.0",
        "1.0.0",
    )


async def test_an_installed_spec_addon_at_its_version_is_in_sync(
    support: Any, gitlab: InMemoryGitLab, hub: Any, identity: Any, clock: Any
) -> None:
    day2 = FakeDay2Addons({NEW: [InstalledAddon("redbull", "cluster-roles", "main")]})
    app = support.build_app(gitlab=gitlab, hub=hub, identity=identity, day2=day2, clock=clock)
    context: Day1Context = app.state.day1
    await create_merged(context, support)
    assert (await context.drift.for_cluster(REF)).state is DriftState.IN_SYNC


async def test_an_addon_at_another_version_is_reported_and_in_sync(
    support: Any, gitlab: InMemoryGitLab, hub: Any, identity: Any, clock: Any
) -> None:
    day2 = FakeDay2Addons({NEW: [InstalledAddon("redbull", "cluster-roles", "2.0.0")]})
    app = support.build_app(gitlab=gitlab, hub=hub, identity=identity, day2=day2, clock=clock)
    context: Day1Context = app.state.day1
    await create_merged(context, support)
    drift = await context.drift.for_cluster(REF)
    assert drift.addon_drift == () and drift.state is DriftState.IN_SYNC
    [difference] = drift.version_differences
    assert (difference.name, difference.installed_version) == ("cluster-roles", "2.0.0")


async def test_day2_down_makes_drift_unknown_not_in_sync(
    context: Day1Context, support: Any, day2: FakeDay2Addons
) -> None:
    # Legacy: a failed day2 call was caught and reported as is_drifted=False.
    await create_merged(context, support)
    day2.unavailable = True
    drift = await context.drift.for_cluster(REF)
    assert drift.state is DriftState.UNKNOWN
    assert drift.is_drifted is None
    assert drift.error is not None
    assert "day2 did not answer" in drift.error
    summary = {d.ref.name: d for d in await context.drift.summary()}
    assert summary[NEW].state is DriftState.UNKNOWN


async def test_a_deleted_spec_makes_drift_unknown(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await create_merged(context, support)
    pid = await support.project_id(gitlab, support.SPECS)
    path = RepoPath("specs/agent-standard.yaml")
    current = await gitlab.read_file(pid, path, "main")
    await gitlab.commit(
        pid,
        branch="main",
        message="drop",
        changes=[FileChange.delete(path, last_commit_id=current.last_commit_id)],
    )
    context.repos[RepoKey.SPECS].forget_files()
    drift = await context.drift.for_cluster(REF)
    assert drift.state is DriftState.UNKNOWN
    assert drift.error == "spec 'agent-standard' no longer exists"


async def test_an_unreadable_spec_makes_drift_unknown(
    context: Day1Context, support: Any, gitlab: InMemoryGitLab
) -> None:
    await create_merged(context, support)
    await support.push(
        gitlab, support.SPECS, branch="main", file="specs/agent-standard.yaml", content="x: [\n"
    )
    context.repos[RepoKey.SPECS].forget_files()
    drift = await context.drift.for_cluster(REF)
    assert drift.state is DriftState.UNKNOWN
    assert drift.error == "spec 'agent-standard' cannot be read"


async def test_a_spec_without_addons_is_in_sync(context: Day1Context, support: Any) -> None:
    await create_merged(context, support, spec_name="agent-single")
    drift = await context.drift.for_cluster(REF)
    assert drift.state is DriftState.IN_SYNC
    assert drift.addon_drift == ()


async def test_a_specs_clusters_are_the_ones_its_header_names(
    context: Day1Context, support: Any
) -> None:
    await create_merged(context, support)
    assert [d.ref.name for d in await context.drift.for_spec("agent-standard")] == [NEW]
    assert await context.drift.for_spec("agent-single") == []
