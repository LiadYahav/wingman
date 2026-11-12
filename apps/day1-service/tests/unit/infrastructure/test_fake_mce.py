"""The fake MCE for DAY1_FAKE_FLEET: coherent with the fixtures, and each scenario as described."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from wingman_core.testing.fixtures import default_fixture_root
from wingman_day1.domain.mce_capacity import (
    ExcludedNodes,
    SpareServers,
    Supply,
    free_pods,
    node_type_supply,
    spare_servers,
)
from wingman_day1.domain.names import HostedClusterNaming, HostedClusterRef
from wingman_day1.domain.node_pools import (
    ClusterMachines,
    NodesByPool,
    NodeState,
    UpdateProgress,
    nodes_by_pool,
)
from wingman_day1.domain.servers import ServerRow
from wingman_day1.infrastructure.fake_fleet import (
    PHASE_SECONDS,
    FakeServerInventory,
    FakeUninstallWorkflow,
    default_fleet_file,
    load_fleet,
)
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.fake_mce import default_mce_file, load_fake_mce

SITE1_A = "ocp4-prod-mce-site1-a"
NAMING = HostedClusterNaming()


def rows() -> list[ServerRow]:
    return load_fleet(default_fleet_file())[0]


def fake(naming: HostedClusterNaming = NAMING) -> FakeHubApi:
    return load_fake_mce(default_mce_file(), servers=rows(), naming=naming)


async def view(
    hub: FakeHubApi, stem: str, *, mce: str = SITE1_A, naming: HostedClusterNaming = NAMING
) -> NodesByPool:
    ref: HostedClusterRef = naming.for_file(stem)
    hosted = await hub.hosted_cluster(mce, namespace=ref.namespace, name=ref.name)
    cp = ref.control_plane_namespace
    assert hosted.agent_namespace is not None
    observed = ClusterMachines(
        hosted_cluster=hosted,
        node_pools=await hub.node_pools(mce, namespace=ref.namespace),
        machines=await hub.machines(mce, namespace=cp),
        machine_sets=await hub.machine_sets(mce, namespace=cp),
        agent_machines=await hub.agent_machines(mce, namespace=cp),
        agents=await hub.agents(mce, namespace=hosted.agent_namespace),
    )
    return nodes_by_pool(ref, observed, rows())


def fixture_clusters() -> list[tuple[str, str]]:
    sites = default_fixture_root() / "gitops-day1/platform-config/sites"
    return sorted(
        (path.stem, path.parent.parent.name)
        for path in sites.glob("*/mces/*/hostedClusters/*.yaml")
    )


@pytest.mark.parametrize(("stem", "mce"), fixture_clusters())
async def test_every_fixture_cluster_is_on_its_mce(stem: str, mce: str) -> None:
    ref = NAMING.for_file(stem)
    hosted = await fake().hosted_cluster(mce, namespace=ref.namespace, name=ref.name)
    assert hosted.agent_namespace == "inventory"


async def test_every_agent_names_a_server_of_the_fake_fleet() -> None:
    names = {row.name.lower() for row in rows()}
    agents = await fake().agents(SITE1_A, namespace="inventory")
    assert agents
    assert {agent.bmh for agent in agents} <= names


async def test_lark_updates_one_pool_in_place_and_has_another_short_a_node() -> None:
    lark = await view(fake(), "ocp4-prod-lark-site1")
    in_place, replace = lark.node_pools
    assert in_place.upgrade_type == "InPlace"
    assert in_place.update is not None
    assert (in_place.update.kind, in_place.update.progress) == ("version", UpdateProgress(3, 1))
    (rebooting,) = [n for n in in_place.nodes if n.current]
    assert rebooting.state is NodeState.NOT_READY
    assert rebooting.activity == "Rebooting for the update (Node condition Ready is Unknown)"
    assert rebooting.server is not None and rebooting.server.name.endswith("DLFAKE0102")
    assert any(p.startswith("AllNodesHealthy: NodeConditionsFailed") for p in in_place.problems)

    assert (replace.upgrade_type, replace.wanted, replace.ready) == ("Replace", 2, 1)
    assert replace.free_agents is not None
    assert (replace.free_agents.matching, replace.free_agents.free) == (3, 0)
    (waiting,) = [n for n in replace.nodes if n.state is NodeState.WAITING]
    assert waiting.waiting_for == (
        "No free Agent matches this NodePool: 3 Agents match its selector, "
        "none is free (2 bound, 1 not approved)"
    )
    assert [row.name for row in lark.unassigned] == ["ocp-dell-r760-site1-64c-512gb-DLFAKE0105"]


async def test_herzi_rolls_out_by_replacing_a_draining_node_with_an_installing_one() -> None:
    herzi = await view(fake(), "ocp4-prod-herzi-site1")
    (pool,) = herzi.node_pools
    states = {(n.state, n.current, n.outdated, n.activity) for n in pool.nodes}
    assert (NodeState.DELETING, True, True, "Draining") in states
    assert (NodeState.INSTALLING, True, False, "Installing: Writing image to disk") in states
    assert [n.state for n in pool.nodes if not n.current] == [NodeState.READY, NodeState.READY]
    assert all(n.outdated for n in pool.nodes if n.state is NodeState.READY)
    assert herzi.unassigned == ()


@pytest.mark.parametrize(
    ("stem", "mce"),
    [("ocp4-prod-hawk-site1", SITE1_A), ("ocp4-prep-amit-site2-a", "ocp4-prep-mce-site2-a")],
)
async def test_the_simple_clusters_are_ready(stem: str, mce: str) -> None:
    found = await view(fake(), stem, mce=mce)
    (pool,) = found.node_pools
    assert pool.update is None
    assert pool.problems == ()
    assert [n.state for n in pool.nodes] == [NodeState.READY, NodeState.READY]
    assert all(n.server is not None for n in pool.nodes)


async def test_the_sandbox_naming_builds_the_same_story_in_its_own_namespaces() -> None:
    sandbox = HostedClusterNaming("")
    lark = await view(fake(sandbox), "ocp4-prod-lark-site1", naming=sandbox)
    assert [len(p.nodes) for p in lark.node_pools] == [3, 2]


async def test_a_completed_uninstall_removes_the_node_and_the_pool_waits_for_an_agent() -> None:
    hub = fake()
    target = "ocp-dell-r660-site1-128c-1024gb-DLFAKE0103"
    assert hub.remove_server(target.upper())
    in_place = (await view(hub, "ocp4-prod-lark-site1")).node_pools[0]
    assert target not in {n.server_name for n in in_place.nodes}
    (backfill,) = [n for n in in_place.nodes if n.state is NodeState.WAITING]
    assert backfill.machine is not None and backfill.machine.endswith("-b0001")
    assert backfill.waiting_for is not None and "none is free (2 bound)" in backfill.waiting_for
    assert not hub.remove_server("ocp-nope")


async def test_the_fake_workflow_tells_the_fake_mce_when_a_run_completes() -> None:
    now = [datetime(2026, 11, 11, 8, 0, tzinfo=UTC)]
    fleet = rows()
    inventory = FakeServerInventory(fleet)
    workflow = FakeUninstallWorkflow(inventory, clock=lambda: now[0])
    removed: list[str] = []
    workflow.after_uninstall(removed.append)
    name = "ocp-dell-r660-site1-128c-1024gb-DLFAKE0101"
    await workflow.start(server_name=name, mce=SITE1_A, namespace=None)
    await workflow.runs()
    assert removed == []
    now[0] += timedelta(seconds=PHASE_SECONDS * 10)
    await workflow.runs()
    assert removed == [name]


def test_a_scenario_the_builder_does_not_know_is_refused(tmp_path: Path) -> None:
    fixture = tmp_path / "mce.yaml"
    fixture.write_text(
        "agent_namespace: inventory\nclusters:\n"
        "  - name: ocp4-prod-lark-site1\n    mce: m\n    version: '4.18'\n    node_pools:\n"
        "      - {infra_env: x, upgrade: Replace, replicas: 1, version: '4.18',"
        " nodes: [{as: dancing}]}\n",
        "utf-8",
    )
    with pytest.raises(ValueError, match="dancing"):
        load_fake_mce(fixture, servers=[], naming=NAMING)
    fixture.write_text("- not a mapping\n", "utf-8")
    with pytest.raises(TypeError, match="clusters"):
        load_fake_mce(fixture, servers=[], naming=NAMING)


async def test_every_convention_mce_of_the_fixtures_has_a_hub_with_nodes() -> None:
    """MCE placement reads each candidate's nodes and pods (ADR-0050)."""
    sites = default_fixture_root() / "gitops-day1/platform-config/sites"
    folders = {p.name for p in sites.glob("*/mces/*") if p.is_dir()}
    hub = fake()
    for mce in folders - {"ocp4-mce-workflow-test"}:
        assert await hub.nodes(mce), mce
    assert (await hub.pods_per_node(SITE1_A))["worker-0"] == 200


async def test_the_demo_hubs_tell_the_placement_story() -> None:
    """site1 prod: -b has room, -a less, -c too little (one worker not ready)."""
    hub = fake()
    mces = ("ocp4-prod-mce-site1-a", "ocp4-prod-mce-site1-b", "ocp4-prod-mce-site1-c")
    free = {}
    for mce in mces:
        counted = free_pods(await hub.nodes(mce), await hub.pods_per_node(mce))
        free[mce] = (counted.free, counted.excluded)
    assert free == {
        "ocp4-prod-mce-site1-a": (150, ExcludedNodes(control_plane=3)),
        "ocp4-prod-mce-site1-b": (
            400,
            ExcludedNodes(control_plane=3, infra=3, unschedulable=1),
        ),
        "ocp4-prod-mce-site1-c": (40, ExcludedNodes(control_plane=3, not_ready=1)),
    }
    assert {m: spare_servers(rows(), m) for m in mces} == {
        "ocp4-prod-mce-site1-a": SpareServers(total=6, usable=6),
        "ocp4-prod-mce-site1-b": SpareServers(total=4, usable=3),
        "ocp4-prod-mce-site1-c": None,
    }


async def test_the_demo_has_a_node_type_short_on_each_of_two_mces() -> None:
    """Two Dell R650: -a has them, -b is one healthy short; two HP Gen12: the other way."""
    hub = fake()
    dell, hp = "dell-r650-site1-96c-768gb", "hp-gen12-site1-64c-512gb"
    needs = [(dell, 2), (hp, 2)]
    supply = {}
    for mce in ("ocp4-prod-mce-site1-a", "ocp4-prod-mce-site1-b", "ocp4-prod-mce-site1-c"):
        agents = await hub.infra_env_agents(mce, infra_envs=[dell, hp], namespace=None)
        supply[mce] = [(t.infra_env, t.status) for t in node_type_supply(needs, agents, rows())]
    assert supply == {
        "ocp4-prod-mce-site1-a": [(dell, Supply.ENOUGH), (hp, Supply.SHORT)],
        "ocp4-prod-mce-site1-b": [(dell, Supply.SHORT), (hp, Supply.ENOUGH)],
        "ocp4-prod-mce-site1-c": [(dell, Supply.SHORT), (hp, Supply.SHORT)],
    }
    assert dell in await hub.infra_envs("ocp4-prod-mce-site1-b", namespace=None)
