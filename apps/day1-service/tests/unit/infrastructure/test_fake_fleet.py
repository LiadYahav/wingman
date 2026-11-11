"""The fake fleet: its fixture is server-scan-shaped and fits the fixture clusters; runs walk."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.errors import (
    AmbiguousStartError,
    ServerNotFoundError,
    ServerScanUnavailableError,
    UninstallAlreadyRunningError,
    WorkflowsUnavailableError,
)
from wingman_day1.domain.names import HostedClusterNaming
from wingman_day1.domain.servers import UNINSTALL_HOLDER, ServerRow, uninstall_workflow_id
from wingman_day1.domain.workflows import WorkflowRun
from wingman_day1.infrastructure.fake_fleet import (
    DEMO_PHASES,
    PHASE_SECONDS,
    FakeServerInventory,
    FakeUninstallWorkflow,
    default_fleet_file,
    load_fleet,
)

MCE = "ocp4-prod-mce-site1-a"
NODE = ServerRow(
    id="srv_1",
    name="ocp-dell-r660-site1-64c-512gb-DLFAKE0001",
    state="INSTALLED",
    health="HEALTHY",
    cluster_name="ocp4-prod-lark-site1",
    mce=MCE,
)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 11, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def fleet(*rows: ServerRow) -> tuple[FakeServerInventory, FakeUninstallWorkflow, Clock]:
    clock = Clock()
    inventory = FakeServerInventory(rows or (NODE,))
    return inventory, FakeUninstallWorkflow(inventory, clock=clock), clock


def fixture_clusters() -> dict[str, str]:
    """Each fixture cluster's two server-scan names, and the MCE folder it is in."""
    sites = default_fixture_root() / "gitops-day1/platform-config/sites"
    naming = HostedClusterNaming()
    names: dict[str, str] = {}
    for path in sites.glob("*/mces/*/hostedClusters/*.yaml"):
        ref = naming.for_file(path.stem)
        mce = path.parent.parent.name
        names[ref.name] = names[ref.cluster_name] = mce
    return names


def test_the_fixture_fleet_reads_as_server_scan_rows_and_fits_the_fixture_clusters() -> None:
    rows, runs = load_fleet(default_fleet_file())
    assert len({row.id for row in rows}) == len(rows), "server ids are unique"
    clusters = fixture_clusters()
    in_clusters = [row for row in rows if row.cluster_name]
    for row in in_clusters:
        assert row.cluster_name in clusters, f"{row.name}: {row.cluster_name} is no fixture cluster"
        assert row.mce == clusters[row.cluster_name], f"{row.name} is on another MCE"
        assert row.name.startswith(f"ocp-{row.vendor}-"), row.name
        assert row.serial and row.name.endswith(row.serial), row.name
    assert any(row.cluster_name is None for row in rows), "some servers are free"
    assert {run.status for run in runs} == {"failed"}


def test_the_lark_cluster_shows_every_kind_of_node() -> None:
    rows, _ = load_fleet(default_fleet_file())
    lark = [r for r in rows if r.cluster_name in {"ocp4-prod-lark-site1", "prod-lark-site1"}]
    assert len(lark) == 5
    assert {"WARNING", "HEALTHY"} <= {r.health for r in lark}
    assert any(r.maintenance for r in lark)
    assert any(r.stale for r in lark)
    assert {r.cluster_name for r in lark} == {"ocp4-prod-lark-site1", "prod-lark-site1"}


def test_the_fixture_holds_nothing_real() -> None:
    text = default_fleet_file().read_text(encoding="utf-8")
    for line in text.splitlines():
        if "bmc_host:" in line:
            assert line.split(":", 1)[1].strip().startswith("192.0.2."), line
    assert "FAKE" in text


def test_a_run_names_a_server_the_fixture_has(tmp_path: Path) -> None:
    fixture = tmp_path / "servers.yaml"
    fixture.write_text("items: []\nruns:\n  - {server: ocp-nope, status: FAILED}\n", "utf-8")
    with pytest.raises(ValueError, match="ocp-nope"):
        load_fleet(fixture)
    fixture.write_text("- not a mapping\n", "utf-8")
    with pytest.raises(TypeError, match="items"):
        load_fleet(fixture)


async def test_an_uninstall_walks_the_demo_phases_then_frees_the_server() -> None:
    inventory, workflow, clock = fleet()
    started = await workflow.start(server_name=NODE.name.upper(), mce=MCE, namespace=None)
    workflow_id = uninstall_workflow_id(NODE.name)
    assert started == WorkflowRun(workflow_id, "running")
    assert (await inventory.rows())[0].reserved_by == UNINSTALL_HOLDER
    seen = []
    for _ in DEMO_PHASES:
        run = await workflow.run(workflow_id)
        assert run is not None
        seen.append(run.phase)
        clock.advance(PHASE_SECONDS)
    assert seen == list(DEMO_PHASES)
    done = await workflow.run(workflow_id)
    assert done is not None
    assert done.status == "completed"
    freed = (await inventory.rows())[0]
    assert (freed.state, freed.cluster_name, freed.mce, freed.reserved_by) == (
        "AVAILABLE",
        None,
        None,
        None,
    )
    assert [r.status for r in await workflow.runs()] == ["completed"]


async def test_reading_the_inventory_moves_the_runs_on_too() -> None:
    inventory, workflow, clock = fleet()
    await workflow.start(server_name=NODE.name, mce=MCE, namespace=None)
    clock.advance(PHASE_SECONDS * (len(DEMO_PHASES) + 1))
    assert (await inventory.rows())[0].cluster_name is None


async def test_a_second_start_while_one_runs_is_refused_like_the_orchestrators_409() -> None:
    _, workflow, clock = fleet()
    await workflow.start(server_name=NODE.name, mce=MCE, namespace=None)
    with pytest.raises(UninstallAlreadyRunningError):
        await workflow.start(server_name=NODE.name, mce=MCE, namespace=None)
    clock.advance(PHASE_SECONDS * (len(DEMO_PHASES) + 1))
    await workflow.start(server_name=NODE.name, mce=MCE, namespace="inventory")
    assert [s["namespace"] for s in workflow.starts] == [None, None, "inventory"]


async def test_an_unknown_server_fails_its_run_as_the_real_workflow_does() -> None:
    _, workflow, _ = fleet()
    started = await workflow.start(server_name="ocp-nope", mce=MCE, namespace=None)
    assert started.status == "running"
    run = await workflow.run(started.workflow_id)
    assert run is not None
    assert run.status == "failed"
    assert run.error is not None
    assert run.error.startswith("ServerNotFoundError")


async def test_seeded_runs_stay_as_seeded_newest_first() -> None:
    clock = Clock()
    seeded = [
        WorkflowRun("uninstall-server-from-hc-b", "failed", phase="draining-node", error="E: x"),
        WorkflowRun("uninstall-server-from-hc-a", "completed"),
    ]
    workflow = FakeUninstallWorkflow(FakeServerInventory(), clock=clock, runs=seeded)
    clock.advance(3600)
    assert [r.workflow_id for r in await workflow.runs()] == [r.workflow_id for r in seeded]
    assert await workflow.run("uninstall-server-from-hc-b") == seeded[0]
    assert await workflow.run("uninstall-server-from-hc-nope") is None


async def test_the_fakes_fail_like_the_real_systems() -> None:
    inventory, workflow, _ = fleet()
    with pytest.raises(ServerNotFoundError):
        await inventory.server("srv_nope")
    workflow.fail_start = AmbiguousStartError("lost (fake)")
    with pytest.raises(AmbiguousStartError):
        await workflow.start(server_name=NODE.name, mce=MCE, namespace=None)
    workflow.unavailable = True
    with pytest.raises(WorkflowsUnavailableError):
        await workflow.runs()
    inventory.unavailable = True
    with pytest.raises(ServerScanUnavailableError):
        await inventory.rows()


async def test_one_server_reads_what_the_row_says_now() -> None:
    inventory, _, _ = fleet()
    inventory.replace(dataclasses.replace(NODE, cluster_name="ocp4-prod-hawk-site1"))
    detail = await inventory.server(NODE.id)
    assert detail.cluster_name == "ocp4-prod-hawk-site1"
    assert inventory.server_reads == 1
