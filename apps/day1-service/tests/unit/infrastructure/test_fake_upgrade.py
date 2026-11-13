"""FakeUpgradeWorkflow on the fixture's script (DAY1_FAKE_FLEET, ADR-0055).

A started run walks the fixture's steps on the injected clock; a step that
waits for a decision stays until it comes, and any other decision is refused
as the run's validator would. Phases and texts are the fixture's.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from wingman_day1.domain.errors import (
    ResourceNotFoundError,
    UpgradeAlreadyRunningError,
    UpgradeDecisionRefusedError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.upgrades import (
    UpgradeDecision,
    UpgradeRequest,
    UpgradeRun,
    upgrade_workflow_id,
)
from wingman_day1.infrastructure.fake_upgrade import FakeUpgradeWorkflow
from wingman_day1.infrastructure.fake_upgrade_script import (
    default_upgrade_file,
    load_upgrade_script,
)

LARK = "ocp4-prod-lark-site1"
RUN = upgrade_workflow_id(LARK)
POOLS = (
    "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb",
    "prod-lark-site1-dell-r760-site1-64c-512gb-20tb",
)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def fake(clock: Clock) -> FakeUpgradeWorkflow:
    return FakeUpgradeWorkflow(load_upgrade_script(default_upgrade_file()), clock=clock)


def start(*, workers_to_target: bool | None = None) -> UpgradeRequest:
    return UpgradeRequest(
        cluster=LARK,
        requested_by="alice",
        target_version="4.18.56",
        workers_to_target=workers_to_target,
    )


async def read(fake: FakeUpgradeWorkflow) -> UpgradeRun:
    run = await fake.run(RUN)
    assert run is not None
    return run


async def wait_for(fake: FakeUpgradeWorkflow, clock: Clock, phase: str) -> UpgradeRun:
    for _ in range(100):
        run = await read(fake)
        if run.phase == phase:
            return run
        clock.advance(1)
    raise AssertionError(f"the run never reached {phase}")


async def test_targets_are_the_fixtures_with_a_default_for_any_other_cluster(
    fake: FakeUpgradeWorkflow,
) -> None:
    lark = await fake.targets(LARK)
    assert (lark.mce, [t.version for t in lark.targets]) == ("ocp4-prod-mce-site1-a", ["4.18.56"])
    assert lark.nodepool_order == POOLS
    assert (await fake.targets("ocp4-prod-owl-site1")).targets == ()
    other = await fake.targets("ocp4-prod-anything-site9")
    assert (other.cluster, len(other.targets)) == ("ocp4-prod-anything-site9", 1)


async def test_a_run_walks_to_done_through_its_decisions(
    fake: FakeUpgradeWorkflow, clock: Clock
) -> None:
    started = await fake.start(start())
    assert (started.workflow_id, started.status) == (RUN, "running")
    first = await read(fake)
    assert (first.phase, first.current_step) == ("planning", None)
    waiting = await wait_for(fake, clock, "awaiting-approval")
    assert waiting.waiting_for is not None and waiting.waiting_for.startswith("approve: 4.18.22")
    clock.advance(600)
    assert (await read(fake)).phase == "awaiting-approval", "it waits for a person"
    await fake.decide(RUN, UpgradeDecision.APPROVE, by="alice")
    stepping = await wait_for(fake, clock, "control-plane-step")
    assert (stepping.current_step, stepping.control_plane_version) == (0, "4.18.22")
    confirm = await wait_for(fake, clock, "awaiting-day2-confirm")
    assert confirm.control_plane_version == "4.18.56"
    await fake.decide(RUN, UpgradeDecision.CONFIRM_DAY2, by="bob", reason="synced")
    for pool in POOLS:
        waiting = await wait_for(fake, clock, "awaiting-continue")
        assert (waiting.current_step, waiting.current_nodepool) == (1, pool)
        await fake.decide(RUN, UpgradeDecision.CONTINUE, by="carol")
        rolled = await wait_for(fake, clock, "nodepool-gate")
        assert rolled.nodepool_versions[pool] == "4.18.56"
    clock.advance(60)
    done = await read(fake)
    assert (done.status, done.outcome, done.phase, done.steps_completed) == (
        "completed",
        "done",
        None,
        2,
    )
    assert [line.event for line in done.log][:2] == ["started", "approve"]
    assert [d[1] for d in fake.decisions] == ["approve", "confirm-day2", "continue", "continue"]


async def test_a_decision_the_run_does_not_wait_for_is_refused_in_words(
    fake: FakeUpgradeWorkflow, clock: Clock
) -> None:
    await fake.start(start())
    await wait_for(fake, clock, "awaiting-approval")
    for decision in (UpgradeDecision.CONTINUE, UpgradeDecision.RETRY, UpgradeDecision.PAUSE):
        with pytest.raises(UpgradeDecisionRefusedError, match="awaiting-approval, waiting for"):
            await fake.decide(RUN, decision, by="alice")
    with pytest.raises(UpgradeDecisionRefusedError, match="no pending action"):
        await fake.decide_action(RUN, "act-1", approve=True, by="alice")
    assert (await read(fake)).phase == "awaiting-approval"


async def test_pause_holds_the_clock_and_resume_carries_on(
    fake: FakeUpgradeWorkflow, clock: Clock
) -> None:
    await fake.start(start())
    await wait_for(fake, clock, "awaiting-approval")
    await fake.decide(RUN, UpgradeDecision.APPROVE, by="alice")
    await fake.decide(RUN, UpgradeDecision.PAUSE, by="bob", reason="change freeze")
    paused = await read(fake)
    assert (paused.phase, paused.paused, paused.waiting_for) == (
        "paused",
        True,
        "resume: paused by bob",
    )
    clock.advance(600)
    assert (await read(fake)).phase == "paused"
    with pytest.raises(UpgradeDecisionRefusedError):
        await fake.decide(RUN, UpgradeDecision.PAUSE, by="bob")
    await fake.decide(RUN, UpgradeDecision.RESUME, by="bob")
    assert (await read(fake)).phase == "waiting-for-slot"


async def test_abort_cancels_before_approval_and_aborts_after(
    fake: FakeUpgradeWorkflow, clock: Clock
) -> None:
    await fake.start(start())
    await fake.decide(RUN, UpgradeDecision.ABORT, by="alice", reason="wrong target")
    assert (await read(fake)).outcome == "cancelled"
    with pytest.raises(ResourceNotFoundError):
        await fake.decide(RUN, UpgradeDecision.APPROVE, by="alice")
    await fake.start(start())
    await wait_for(fake, clock, "awaiting-approval")
    await fake.decide(RUN, UpgradeDecision.APPROVE, by="alice")
    await fake.decide(RUN, UpgradeDecision.ABORT, by="alice", reason="a bad day")
    aborted = await read(fake)
    assert (aborted.outcome, aborted.steps_completed) == ("aborted", 0)


async def test_one_open_run_per_cluster_and_continue_may_name_the_next_pool(
    fake: FakeUpgradeWorkflow, clock: Clock
) -> None:
    await fake.start(start())
    with pytest.raises(UpgradeAlreadyRunningError):
        await fake.start(start())
    await wait_for(fake, clock, "awaiting-approval")
    await fake.decide(RUN, UpgradeDecision.APPROVE, by="alice")
    await wait_for(fake, clock, "awaiting-day2-confirm")
    await fake.decide(RUN, UpgradeDecision.CONFIRM_DAY2, by="alice")
    waiting = await wait_for(fake, clock, "awaiting-continue")
    assert waiting.current_nodepool == POOLS[0]
    with pytest.raises(UpgradeDecisionRefusedError, match="not waiting to roll"):
        await fake.decide(RUN, UpgradeDecision.CONTINUE, by="alice", nodepool="nope")
    await fake.decide(RUN, UpgradeDecision.CONTINUE, by="alice", nodepool=POOLS[1])
    assert (await read(fake)).current_nodepool == POOLS[1]
    plan = (await read(fake)).plan
    assert plan is not None and plan.steps[1].nodepools == (POOLS[1], POOLS[0])


async def test_control_plane_only_has_no_nodepool_steps(
    fake: FakeUpgradeWorkflow, clock: Clock
) -> None:
    await fake.start(start(workers_to_target=False))
    run = await read(fake)
    assert run.plan is not None and [s.kind for s in run.plan.steps] == ["control-plane"]


async def test_an_unavailable_fake_fails_every_call(fake: FakeUpgradeWorkflow) -> None:
    fake.unavailable = True
    with pytest.raises(WorkflowsUnavailableError):
        await fake.targets(LARK)
    with pytest.raises(WorkflowsUnavailableError):
        await fake.run(RUN)
