"""FakeScaleWorkflow: a sample update-nodepool on the injected clock (ADR-0062)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from wingman_day1.domain.errors import ScaleAlreadyRunningError, WorkflowsUnavailableError
from wingman_day1.domain.scale import ScaleRequest, scale_workflow_id
from wingman_day1.infrastructure.fake_scale import (
    DOWN_PHASES,
    PARENT_PHASES,
    UP_PHASES,
    FakePool,
    FakeScaleWorkflow,
)

CLUSTER = "ocp4-prod-alpha"
RUN = scale_workflow_id(CLUSTER)
POOLS = (
    FakePool("alpha-zone-a", "cisco-64c-zone-a", 3),
    FakePool("alpha-zone-b", "cisco-64c-zone-b", 3, "fewest-pods"),
    FakePool("alpha-gpu", "h200", 1),
)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def step(self, phases: int = 1) -> None:
        self.now += timedelta(seconds=4 * phases)


async def source(_cluster: str) -> Sequence[FakePool]:
    return POOLS


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def fake(clock: Clock) -> FakeScaleWorkflow:
    return FakeScaleWorkflow(clock=clock, pools=source)


async def test_a_scale_down_walks_the_parent_then_its_child(
    fake: FakeScaleWorkflow, clock: Clock
) -> None:
    started = await fake.start(ScaleRequest("mce", CLUSTER, 2, nodepool="alpha-zone-b"))
    assert (started.workflow_id, started.status) == (RUN, "running")
    seen = []
    for _ in range(len(PARENT_PHASES) + len(DOWN_PHASES)):
        run = await fake.run(RUN)
        assert run is not None and run.status == "running"
        seen.append((run.phase, run.child.phase if run.child else None))
        clock.step()
    assert seen == [(p, None) for p in PARENT_PHASES] + [("scaling-down", p) for p in DOWN_PHASES]
    done = await fake.run(RUN)
    assert done is not None and done.result is not None
    assert (done.status, done.direction) == ("completed", "down")
    assert [(c.name, c.before, c.after) for c in done.result.nodepools] == [("alpha-zone-b", 3, 2)]
    assert (done.result.nodepool, done.result.infra_env_kind) == ("alpha-zone-b", None)
    assert [(c.nodepool, c.policy) for c in done.result.chosen] == [("alpha-zone-b", "fewest-pods")]
    assert done.result.deleting == ("alpha-zone-b-m2",)


async def test_a_scale_down_that_names_its_servers_removes_exactly_those(
    fake: FakeScaleWorkflow, clock: Clock
) -> None:
    named = ("ocp-cisco-64c-ZB0001", "ocp-cisco-64c-zb0002")
    await fake.start(ScaleRequest("mce", CLUSTER, 1, nodepool="alpha-zone-b", server_names=named))
    clock.step(len(PARENT_PHASES) + len(DOWN_PHASES))
    done = await fake.run(RUN)
    assert done is not None and done.result is not None
    assert [(c.server, c.policy, c.reason) for c in done.result.chosen] == [
        ("ocp-cisco-64c-zb0001", "named", "named: ocp-cisco-64c-ZB0001"),
        ("ocp-cisco-64c-zb0002", "named", "named: ocp-cisco-64c-zb0002"),
    ]
    assert done.result.deleting == ("alpha-zone-b-m0", "alpha-zone-b-m1")


async def test_a_scale_down_with_a_policy_of_its_own_ranks_by_it_ahead_of_the_nodepools(
    fake: FakeScaleWorkflow, clock: Clock
) -> None:
    own = ScaleRequest(
        "mce", CLUSTER, 2, nodepool="alpha-zone-b", scale_down_policy="least-utilized"
    )
    await fake.start(own)
    clock.step(len(PARENT_PHASES) + len(DOWN_PHASES))
    done = await fake.run(RUN)
    assert done is not None and done.result is not None
    assert [c.scale_down_policy for c in done.result.nodepools] == ["least-utilized"]
    assert [c.policy for c in done.result.chosen] == ["least-utilized"]
    assert done.result.ignored == ()


async def test_a_policy_sent_with_a_scale_up_is_ignored_and_said_so(
    fake: FakeScaleWorkflow, clock: Clock
) -> None:
    up = ScaleRequest(
        "mce", CLUSTER, 4, nodepool="alpha-zone-b", scale_down_policy="least-utilized"
    )
    await fake.start(up)
    clock.step(len(PARENT_PHASES) + len(UP_PHASES))
    done = await fake.run(RUN)
    assert done is not None and done.result is not None
    assert [c.scale_down_policy for c in done.result.nodepools] == ["fewest-pods"]
    assert done.result.ignored == ("scale_down_policy least-utilized: the NodePool scales up",)


async def test_a_scale_up_by_name_sets_that_nodepool_and_the_next_run_starts_from_it(
    fake: FakeScaleWorkflow, clock: Clock
) -> None:
    await fake.start(ScaleRequest("mce", CLUSTER, 4, nodepool="alpha-gpu"))
    clock.step(len(PARENT_PHASES))
    run = await fake.run(RUN)
    assert run is not None and run.child is not None
    assert (run.phase, run.child.phase) == ("scaling-up", UP_PHASES[0])
    clock.step(len(UP_PHASES))
    done = await fake.run(RUN)
    assert done is not None and done.result is not None
    assert [(c.name, c.before, c.after) for c in done.result.nodepools] == [("alpha-gpu", 1, 4)]
    await fake.start(ScaleRequest("mce", CLUSTER, 4, nodepool="alpha-gpu"))
    clock.step(len(PARENT_PHASES))
    again = await fake.run(RUN)
    assert again is not None and (again.status, again.direction) == ("completed", "none")


async def test_one_run_per_cluster_and_none_while_it_upgrades(clock: Clock) -> None:
    upgrading = {CLUSTER}
    fake = FakeScaleWorkflow(clock=clock, pools=source, upgrading=upgrading.__contains__)
    with pytest.raises(ScaleAlreadyRunningError, match="upgrade-cluster-"):
        await fake.start(ScaleRequest("mce", CLUSTER, 2, nodepool="alpha-gpu"))
    upgrading.clear()
    await fake.start(ScaleRequest("mce", CLUSTER, 2, nodepool="alpha-gpu"))
    with pytest.raises(ScaleAlreadyRunningError, match="already in flight"):
        await fake.start(ScaleRequest("mce", CLUSTER, 3, nodepool="alpha-gpu"))
    assert len(fake.started) == 1


async def test_a_nodepool_the_cluster_lacks_fails_the_run_in_words(
    fake: FakeScaleWorkflow, clock: Clock
) -> None:
    await fake.start(ScaleRequest("mce", CLUSTER, 2, nodepool="alpha-dell"))
    clock.step(len(PARENT_PHASES))
    run = await fake.run(RUN)
    assert run is not None
    assert (run.status, run.phase) == ("failed", "reading-nodepools")
    assert run.error is not None and "no NodePool alpha-dell" in run.error


async def test_no_run_is_none_and_a_down_orchestrator_is_unavailable(clock: Clock) -> None:
    assert await FakeScaleWorkflow(clock=clock).run(RUN) is None
    down = FakeScaleWorkflow(clock=clock, unavailable=True)
    with pytest.raises(WorkflowsUnavailableError):
        await down.start(ScaleRequest("mce", CLUSTER, 2, nodepool="x"))
