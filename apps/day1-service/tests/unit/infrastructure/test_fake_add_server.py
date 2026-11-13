"""FakeAddServerWorkflow and the fake herzi (ADR-0057): what the local demo shows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from wingman_day1.domain.add_server import AddServerRequest
from wingman_day1.domain.errors import AddServerAlreadyRunningError, WorkflowsUnavailableError
from wingman_day1.domain.servers import ServerRow
from wingman_day1.infrastructure.fake_add_server import FakeAddServerWorkflow, HerziScript
from wingman_day1.infrastructure.fake_fleet import (
    FakeServerInventory,
    default_fleet_file,
    load_fleet,
)
from wingman_day1.infrastructure.fake_inventory_demo import (
    default_inventory_file,
    fake_add_server,
    load_inventory_demo,
)

MCE = "ocp4-prod-mce-site1-a"
POOL = "dell-r650-site1-96c-768gb"
PHASES = ("validating-infraenv", "acquiring-server", "registering-bmh")


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def free(name: str, **fields: object) -> ServerRow:
    values: dict[str, object] = {"id": f"srv_{name}", "name": name, "state": "AVAILABLE",
                                 "health": "HEALTHY"}  # fmt: skip
    values.update(fields)
    return ServerRow(**values)  # ty: ignore[invalid-argument-type]


def setup(
    *rows: ServerRow, herzi: HerziScript | None = None
) -> tuple[Clock, FakeServerInventory, FakeAddServerWorkflow]:
    clock = Clock()
    inventory = FakeServerInventory(rows)
    workflow = FakeAddServerWorkflow(
        inventory, clock=clock, phases=PHASES, phase_seconds=10, herzi=herzi
    )
    return clock, inventory, workflow


async def test_a_pool_draw_takes_a_free_server_and_leaves_it_in_the_mces_inventory() -> None:
    clock, inventory, workflow = setup(free(f"ocp-{POOL}-A"), free("ocp-other-B"))
    result = await workflow.start(AddServerRequest(MCE, POOL, None, count=1))
    [run] = result.runs
    assert (result.started, run.slot) == (1, 1)
    assert run.workflow_id == f"add-server-to-mce-{MCE}_{POOL}_1"
    clock.advance(10)
    detail = await workflow.run(run.workflow_id)
    assert detail is not None
    assert (detail.phase, detail.server_name) == ("acquiring-server", f"ocp-{POOL}-A")
    taken = inventory.by_name(f"ocp-{POOL}-A")
    assert taken is not None
    assert (taken.reserved_by, taken.reserved_for_mce) == ("add-server-to-mce", MCE)
    clock.advance(30)
    [listed] = await workflow.runs()
    assert listed.status == "completed"
    done = inventory.by_name(f"ocp-{POOL}-A")
    assert done is not None
    assert (done.state, done.mce) == ("INSTALLED_TO_INVENTORY", MCE)


async def test_two_draws_take_two_servers_and_then_none_is_left() -> None:
    clock, _, workflow = setup(free(f"ocp-{POOL}-A"), free(f"ocp-{POOL}-B"))
    await workflow.start(AddServerRequest(MCE, POOL, None, count=3))
    clock.advance(15)
    runs = {r.workflow_id[-1]: await workflow.run(r.workflow_id) for r in await workflow.runs()}
    assert {k: (v.status, v.server_name) for k, v in runs.items() if v} == {
        "1": ("running", f"ocp-{POOL}-A"),
        "2": ("running", f"ocp-{POOL}-B"),
        "3": ("failed", None),
    }
    third = runs["3"]
    assert third is not None and third.error is not None
    assert third.error.startswith("ServerNotAvailableError")


async def test_a_named_install_fails_on_a_locked_server_as_the_workflow_does() -> None:
    locked = free(f"ocp-{POOL}-L", reserved_by="add-server-to-mce")
    clock, _, workflow = setup(locked, free(f"ocp-{POOL}-M", maintenance=True))
    result = await workflow.start(
        AddServerRequest(MCE, POOL, None, server_names=(f"ocp-{POOL}-L", f"ocp-{POOL}-M"))
    )
    assert [r.server_name for r in result.runs] == [f"ocp-{POOL}-L", f"ocp-{POOL}-M"]
    clock.advance(10)
    reads = [await workflow.run(r.workflow_id) for r in result.runs]
    errors = [read.error if read is not None else None for read in reads]
    assert errors[0] is not None and errors[0].startswith("ServerReservedError")
    assert errors[1] is not None and errors[1].startswith("ServerNotAvailableError")


async def test_a_named_server_already_installing_is_answered_already_running() -> None:
    _, _, workflow = setup(free(f"ocp-{POOL}-A"))
    request = AddServerRequest(MCE, POOL, None, server_names=(f"ocp-{POOL}-A",))
    await workflow.start(request)
    again = await workflow.start(request)
    assert (again.started, again.already_running) == (0, 1)


async def test_every_slot_busy_is_a_conflict() -> None:
    _, _, workflow = setup()
    await workflow.start(AddServerRequest(MCE, POOL, None, count=20))
    for _ in range(4):
        await workflow.start(AddServerRequest(MCE, POOL, None, count=20))
    with pytest.raises(AddServerAlreadyRunningError):
        await workflow.start(AddServerRequest(MCE, POOL, None, count=1))


async def test_herzi_starts_pool_draws_and_waits_after_finding_no_server() -> None:
    herzi = HerziScript(
        MCE,
        POOL,
        first_after=timedelta(seconds=5),
        every=timedelta(seconds=60),
        probe=timedelta(seconds=600),
    )
    clock, _, workflow = setup(free(f"ocp-{POOL}-A"), herzi=herzi)
    assert await workflow.runs() == []
    clock.advance(5)
    assert len(await workflow.runs()) == 1, "herzi's first draw"
    clock.advance(60)
    runs = await workflow.runs()
    assert len(runs) == 2
    clock.advance(30)
    newest = await workflow.run(runs[0].workflow_id)
    assert newest is not None and newest.status == "failed", "no server left for the second"
    clock.advance(300)
    assert len(await workflow.runs()) == 2, "it waits after a run found no server"
    clock.advance(400)
    assert len(await workflow.runs()) == 3, "then probes again"


async def test_an_unreachable_fake_fails_reads_and_starts() -> None:
    _, _, workflow = setup()
    workflow.unavailable = True
    with pytest.raises(WorkflowsUnavailableError):
        await workflow.runs()


async def test_the_demo_adds_its_servers_and_past_runs() -> None:
    clock = Clock()
    rows, _ = load_fleet(default_fleet_file())
    inventory = FakeServerInventory(rows)
    workflow = fake_add_server(inventory, clock=clock)
    demo = load_inventory_demo(default_inventory_file(), now=clock())
    assert all(inventory.by_id(row.id) == row for row in demo.rows)
    locked = inventory.by_name("ocp-dell-r650-site1-96c-768gb-DLFAKE0812")
    assert locked is not None and locked.reserved_by == "add-server-to-mce"
    runs = await workflow.runs()
    assert [r.status for r in runs] == ["failed", "completed"]
    assert demo.herzi is not None and demo.herzi.mce == MCE
    clock.advance(demo.herzi.first_after.total_seconds())
    assert len(await workflow.runs()) == 3, "herzi's first draw"
