"""The join of an MCE's objects into nodes by NodePool, rule by rule (contract §1, ADR-0038)."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

import pytest

from wingman_day1.domain.machines import (
    AGENT_MACHINE_REF_LABEL,
    BMH_LABEL,
    AgentMachineObservation,
    AgentObservation,
    MachineObservation,
    MachineSetObservation,
)
from wingman_day1.domain.names import HostedClusterNaming
from wingman_day1.domain.node_pools import (
    ClusterMachines,
    FreeAgents,
    NodeState,
    PoolUpdate,
    ServerFinder,
    UpdateProgress,
    activity,
    degraded_node,
    deletion_step,
    free_agents,
    is_current,
    missing_nodes,
    node_state,
    nodes_by_pool,
    pool_problems,
    pool_update,
    waiting_for,
    why_not_free,
)
from wingman_day1.domain.selectors import LabelSelector
from wingman_day1.domain.servers import ServerRow
from wingman_day1.domain.status import (
    Autoscaling,
    Condition,
    HostedClusterObservation,
    NodePoolObservation,
)

HOSTED = HostedClusterNaming().for_file("ocp4-prod-lark-site1")
NS = HOSTED.namespace
POOL = "prod-lark-site1-dell"
INFRA_ENV = "infraenvs.agent-install.openshift.io"
SELECTOR = LabelSelector(match_labels=((INFRA_ENV, "dell"),))
TRUE, FALSE = "True", "False"
IN_PROGRESS = (
    "Nodepool update in progress. Target Config version: 6c1f2b. Total Nodes: 3. Upgraded: 1"
)


def pool(**changes: object) -> NodePoolObservation:
    base = NodePoolObservation(
        name=POOL,
        desired_replicas=2,
        current_replicas=2,
        replicas=2,
        upgrade_type="Replace",
        version="4.18.22",
        agent_selector=SELECTOR,
    )
    return dataclasses.replace(base, **changes)


def machine(name: str, **changes: object) -> MachineObservation:
    base = MachineObservation(
        name=name,
        node_pool=f"{NS}/{POOL}",
        machine_set=f"{POOL}-new",
        infrastructure_ref=name,
        provider_id=f"agent://agent-{name}",
        phase="Running",
        node_name=f"node-{name}",
        conditions=(Condition("NodeHealthy", TRUE),),
    )
    return dataclasses.replace(base, **changes)


def agent_machine(
    name: str, *, agent: str | None = None, **changes: object
) -> AgentMachineObservation:
    reserved = Condition(
        "AgentReserved", TRUE if agent else FALSE, "" if agent else "NoSuitableAgents"
    )
    base = AgentMachineObservation(name=name, agent_name=agent, conditions=(reserved,))
    return dataclasses.replace(base, **changes)


def agent(
    name: str, *, bmh: str | None = None, taken_by: str | None = None, **changes: object
) -> AgentObservation:
    labels = {INFRA_ENV: "dell"}
    if bmh:
        labels[BMH_LABEL] = bmh
    if taken_by:
        labels[AGENT_MACHINE_REF_LABEL] = taken_by
    base = AgentObservation(
        name=name,
        labels=labels,
        approved=True,
        state="added-to-existing-cluster",
        stage="Done",
        conditions=(
            Condition("Bound", TRUE if taken_by else FALSE),
            Condition("Connected", TRUE),
            Condition("Validated", TRUE),
            Condition("Installed", TRUE),
        ),
    )
    return dataclasses.replace(base, **changes)


def server(
    name: str, *, cluster: str | None = "ocp4-prod-lark-site1", **changes: object
) -> ServerRow:
    base = ServerRow(
        id=f"srv_{name.lower()}",
        name=name,
        state="INSTALLED",
        health="HEALTHY",
        cluster_name=cluster,
    )
    return dataclasses.replace(base, **changes)


def observed(
    pools: Sequence[NodePoolObservation],
    machines: Sequence[MachineObservation] = (),
    agent_machines: Sequence[AgentMachineObservation] = (),
    agents: Sequence[AgentObservation] | None = None,
    machine_sets: Sequence[MachineSetObservation] = (),
) -> ClusterMachines:
    return ClusterMachines(
        hosted_cluster=HostedClusterObservation(
            HOSTED.name, NS, None, "4.18.22", agent_namespace="inventory"
        ),
        node_pools=pools,
        machines=machines,
        machine_sets=machine_sets,
        agent_machines=agent_machines,
        agents=agents,
    )


def ready_node(
    name: str, server_name: str
) -> tuple[MachineObservation, AgentMachineObservation, AgentObservation]:
    return (
        machine(name, provider_id=f"agent://a-{name}"),
        agent_machine(name, agent=f"a-{name}"),
        agent(f"a-{name}", bmh=server_name.lower(), taken_by=name),
    )


# ── Grouping ─────────────────────────────────────────────────────────────────


def test_machines_belong_to_the_pool_their_annotation_names() -> None:
    other = dataclasses.replace(pool(), name="prod-lark-site1-hp")
    machines = [
        machine("m-dell"),
        machine("m-hp", node_pool=f"{NS}/prod-lark-site1-hp"),
        machine("m-elsewhere", node_pool=f"hcp-other/{POOL}"),
        machine("m-none", node_pool=None),
    ]
    found = nodes_by_pool(
        HOSTED, observed([pool(replicas=1), dataclasses.replace(other, replicas=1)], machines), None
    )
    assert [p.name for p in found.node_pools] == ["prod-lark-site1-dell", "prod-lark-site1-hp"]
    assert [[n.machine for n in p.nodes] for p in found.node_pools] == [["m-dell"], ["m-hp"]]


def test_a_machine_is_followed_to_its_agent_and_server_with_server_scans_spelling() -> None:
    m, am, a = ready_node("m1", "ocp-dell-r660-site1-DL1")
    row = server("ocp-dell-r660-site1-DL1")
    found = nodes_by_pool(HOSTED, observed([pool(replicas=1)], [m], [am], [a]), [row])
    (node,) = found.node_pools[0].nodes
    assert (node.state, node.server, node.server_name) == (NodeState.READY, row, row.name)
    assert node.agent is not None
    assert (node.agent.name, node.agent.state, node.agent.stage) == (
        "a-m1",
        "added-to-existing-cluster",
        "Done",
    )
    assert found.unassigned == ()


def test_without_server_scan_the_server_name_is_the_bare_metal_host() -> None:
    m, am, a = ready_node("m1", "ocp-dell-r660-site1-DL1")
    (node,) = (
        nodes_by_pool(HOSTED, observed([pool(replicas=1)], [m], [am], [a]), None)
        .node_pools[0]
        .nodes
    )
    assert (node.server, node.server_name) == (None, "ocp-dell-r660-site1-dl1")


def test_the_provider_id_finds_the_agent_when_the_agent_machine_has_no_ref() -> None:
    m = machine("m1", provider_id="agent://a-1")
    a = agent("a-1", bmh="ocp-x")
    (node,) = (
        nodes_by_pool(
            HOSTED,
            observed(
                [pool(replicas=1)], [m], [agent_machine("m1", agent=None, conditions=())], [a]
            ),
            None,
        )
        .node_pools[0]
        .nodes
    )
    assert node.agent is not None and node.agent.name == "a-1"
    assert node.state is NodeState.READY


def test_servers_in_the_cluster_no_machine_leads_to_are_unassigned() -> None:
    m, am, a = ready_node("m1", "ocp-a")
    rows = [
        server("ocp-a"),
        server("ocp-left-behind"),
        server("ocp-bare", cluster="prod-lark-site1"),
        server("ocp-elsewhere", cluster="ocp4-prod-hawk-site1"),
    ]
    found = nodes_by_pool(HOSTED, observed([pool(replicas=1)], [m], [am], [a]), rows)
    assert [r.name for r in found.unassigned] == ["ocp-bare", "ocp-left-behind"]
    assert found.leads_to("srv_ocp-a", "ocp-a")
    assert found.leads_to("srv_nope", "OCP-A"), "by the name, ignoring case"
    assert not found.leads_to("srv_ocp-left-behind", "ocp-left-behind")
    assert [r.name for r in found.servers()] == ["ocp-a", "ocp-bare", "ocp-left-behind"]


def test_nodes_are_sorted_by_state_then_by_name() -> None:
    machines = [
        machine("m-ready-b"),
        machine("m-ready-a"),
        machine("m-gone", deleting=True),
        machine("m-wait", provider_id=None, node_name=None),
        machine("m-sick", conditions=(Condition("NodeHealthy", FALSE),)),
    ]
    found = nodes_by_pool(HOSTED, observed([pool(replicas=6)], machines), None)
    nodes = found.node_pools[0].nodes
    assert [(n.state.value, n.machine) for n in nodes] == [
        ("deleting", "m-gone"),
        ("waiting", "m-wait"),
        ("missing", None),
        ("missing", None),
        ("not_ready", "m-sick"),
        ("ready", "m-ready-a"),
        ("ready", "m-ready-b"),
    ]


# ── A node's state ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("m", "am", "a", "state"),
    [
        (machine("m", deleting=True, phase="Failed"), None, None, NodeState.DELETING),
        (machine("m", phase="Failed"), None, None, NodeState.FAILED),
        (machine("m", provider_id=None, node_name=None), None, None, NodeState.WAITING),
        (
            machine("m", provider_id=None, node_name=None),
            agent_machine("m"),
            None,
            NodeState.WAITING,
        ),
        (
            machine("m", node_name=None),
            agent_machine("m", agent="a"),
            agent("a", state="installing-in-progress", conditions=(Condition("Installed", FALSE),)),
            NodeState.INSTALLING,
        ),
        (
            machine("m", node_name=None),
            agent_machine("m", agent="a"),
            agent("a"),
            NodeState.JOINING,
        ),
        (
            machine("m", node_name=None),
            agent_machine(
                "m",
                agent="a",
                conditions=(Condition("AgentReserved", TRUE), Condition("Installed", TRUE)),
            ),
            None,
            NodeState.JOINING,
        ),
        (
            machine("m", conditions=(Condition("NodeHealthy", FALSE),)),
            None,
            None,
            NodeState.NOT_READY,
        ),
        (machine("m", conditions=()), None, None, NodeState.NOT_READY),
        (machine("m"), None, None, NodeState.READY),
    ],
)
def test_the_state_is_the_first_rule_that_holds(
    m: MachineObservation,
    am: AgentMachineObservation | None,
    a: AgentObservation | None,
    state: NodeState,
) -> None:
    assert node_state(m, am, a) is state


def test_the_node_an_in_place_update_names_degraded_has_failed() -> None:
    assert node_state(machine("m"), None, None, degraded=True) is NodeState.FAILED


# ── What is happening to it ──────────────────────────────────────────────────


def test_a_deleting_machine_prefers_v1beta2_deleting() -> None:
    m = machine(
        "m",
        deleting=True,
        conditions=(Condition("DrainingSucceeded", FALSE, "Draining"),),
        v1beta2_conditions=(Condition("Deleting", TRUE, "WaitingForVolumeDetach", "..."),),
    )
    assert deletion_step(m) == "Waiting for volumes to detach"
    unknown = dataclasses.replace(
        m, v1beta2_conditions=(Condition("Deleting", TRUE, "SomethingNew"),)
    )
    assert deletion_step(unknown) == "SomethingNew"


@pytest.mark.parametrize(
    ("conditions", "step"),
    [
        (
            (
                Condition(
                    "DrainingSucceeded", FALSE, "Draining", "Draining the node before deletion"
                ),
            ),
            "Draining",
        ),
        (
            (
                Condition("DrainingSucceeded", TRUE),
                Condition("VolumeDetachSucceeded", FALSE, "WaitingForVolumeDetach"),
            ),
            "Waiting for volumes to detach",
        ),
        (
            (
                Condition("DrainingSucceeded", TRUE),
                Condition("PreTerminateDeleteHookSucceeded", FALSE, "WaitingExternalHook"),
            ),
            "Waiting for the host to return to discovery",
        ),
        (
            (Condition("DrainingSucceeded", FALSE, "DrainingFailed", "pods would be evicted\n"),),
            "Draining failed: pods would be evicted",
        ),
        ((), "Deleting"),
    ],
)
def test_a_deleting_machine_without_v1beta2_shows_its_first_unmet_step(
    conditions: tuple[Condition, ...], step: str
) -> None:
    assert deletion_step(machine("m", deleting=True, conditions=conditions)) == step


@pytest.mark.parametrize(
    ("a", "words"),
    [
        (agent("a", stage="Writing image to disk"), "Installing: Writing image to disk"),
        (
            agent("a", stage=None, state="preparing-for-installation"),
            "Installing (preparing-for-installation)",
        ),
        (None, "Installing"),
    ],
)
def test_an_installing_node_says_the_agents_stage(a: AgentObservation | None, words: str) -> None:
    assert (
        activity(
            NodeState.INSTALLING, machine("m"), a, updating_in_place=False, degraded_reason=None
        )
        == words
    )


def test_a_not_ready_node_reboots_for_an_in_place_update_or_is_just_not_ready() -> None:
    m = machine(
        "m",
        conditions=(
            Condition(
                "NodeHealthy", FALSE, "NodeConditionsFailed", "Node condition Ready is Unknown. "
            ),
        ),
    )
    rebooting = activity(NodeState.NOT_READY, m, None, updating_in_place=True, degraded_reason=None)
    assert rebooting == "Rebooting for the update (Node condition Ready is Unknown)"
    plain = activity(NodeState.NOT_READY, m, None, updating_in_place=False, degraded_reason=None)
    assert plain == "Node not ready: Node condition Ready is Unknown"


def test_the_other_states_say_what_they_are_doing() -> None:
    m = machine("m", failure_reason="CreateError", failure_message="no host")
    say = lambda state, **kw: activity(state, m, None, updating_in_place=False, **kw)  # noqa: E731
    assert say(NodeState.JOINING, degraded_reason=None) == "Joining the cluster"
    assert say(NodeState.FAILED, degraded_reason="disk full") == "disk full"
    assert say(NodeState.FAILED, degraded_reason=None) == "Failed: no host"
    assert say(NodeState.READY, degraded_reason=None) is None
    assert say(NodeState.WAITING, degraded_reason=None) is None


# ── Which node the update works on ───────────────────────────────────────────

UPDATE = PoolUpdate(kind="version", message="m")


@pytest.mark.parametrize(
    ("state", "upgrade", "update", "degraded", "current"),
    [
        (NodeState.NOT_READY, "InPlace", UPDATE, False, True),
        (NodeState.NOT_READY, "InPlace", None, False, False),
        (NodeState.READY, "InPlace", UPDATE, False, False),
        (NodeState.FAILED, "InPlace", UPDATE, True, True),
        (NodeState.DELETING, "Replace", UPDATE, False, True),
        (NodeState.INSTALLING, "Replace", UPDATE, False, True),
        (NodeState.JOINING, "Replace", UPDATE, False, True),
        (NodeState.WAITING, "Replace", UPDATE, False, True),
        (NodeState.NOT_READY, "Replace", UPDATE, False, False),
        (NodeState.DELETING, "Replace", None, False, False),
        (NodeState.DELETING, None, UPDATE, False, False),
    ],
)
def test_current_is_the_node_the_update_works_on_now(
    state: NodeState, upgrade: str | None, update: PoolUpdate | None, degraded: bool, current: bool
) -> None:
    assert is_current(state, upgrade, update, degraded=degraded) is current


def test_a_replace_rollouts_older_revision_is_outdated() -> None:
    sets = [
        MachineSetObservation(f"{POOL}-old", node_pool=f"{NS}/{POOL}", revision=1),
        MachineSetObservation(f"{POOL}-new", node_pool=f"{NS}/{POOL}", revision=2),
    ]
    machines = [machine("m-old", machine_set=f"{POOL}-old"), machine("m-new")]
    found = nodes_by_pool(HOSTED, observed([pool()], machines, machine_sets=sets), None)
    assert {n.machine: n.outdated for n in found.node_pools[0].nodes} == {
        "m-old": True,
        "m-new": False,
    }
    in_place = nodes_by_pool(
        HOSTED, observed([pool(upgrade_type="InPlace")], machines, machine_sets=sets), None
    )
    assert {n.outdated for n in in_place.node_pools[0].nodes} == {None}
    no_revisions = nodes_by_pool(HOSTED, observed([pool()], machines), None)
    assert {n.outdated for n in no_revisions.node_pools[0].nodes} == {None}


def test_machine_sets_are_found_by_annotation_or_else_by_name_or_deployment_label() -> None:
    sets = [
        MachineSetObservation(f"{POOL}-a", deployment=POOL, revision=1),
        MachineSetObservation(f"{POOL}-b", node_pool=f"{NS}/{POOL}", revision=3),
        MachineSetObservation("other-c", node_pool=f"{NS}/other", revision=9),
    ]
    found = nodes_by_pool(
        HOSTED,
        observed([pool(replicas=1)], [machine("m", machine_set=f"{POOL}-a")], machine_sets=sets),
        None,
    )
    assert found.node_pools[0].nodes[0].outdated is True, f"{POOL}-b (revision 3) is the newest"


# ── The update and the problems ──────────────────────────────────────────────


def test_no_update_when_every_updating_condition_is_false() -> None:
    conditions = (
        Condition("UpdatingVersion", FALSE, "AsExpected"),
        Condition("UpdatingConfig", FALSE),
    )
    assert pool_update(conditions) is None
    assert pool_update(()) is None


def test_the_first_updating_condition_that_is_not_false_is_the_update() -> None:
    conditions = (
        Condition("UpdatingVersion", FALSE),
        Condition("UpdatingConfig", TRUE, "AsExpected", IN_PROGRESS),
        Condition("UpdatingPlatformMachineTemplate", TRUE, "AsExpected", "x"),
    )
    assert pool_update(conditions) == PoolUpdate(
        kind="config", message=IN_PROGRESS, progress=UpdateProgress(total=3, updated=1)
    )


def test_an_older_operators_unknown_status_and_annotation_progress() -> None:
    conditions = (Condition("UpdatingVersion", "unknown", "", "Updating Version, Target: 6c1f2b"),)
    sets = [MachineSetObservation(POOL, upgrade_in_progress=IN_PROGRESS)]
    update = pool_update(conditions, sets)
    assert update == PoolUpdate("version", "Updating Version, Target: 6c1f2b", UpdateProgress(3, 1))
    machine_template = (Condition("UpdatingPlatformMachineTemplate", TRUE, "", "Updating"),)
    assert pool_update(machine_template) == PoolUpdate("machine_template", "Updating")


def test_a_failed_in_place_update_is_shown_failed_with_its_degraded_node() -> None:
    message = "Node worker-2 in nodepool degraded: disk full on /var\n"
    conditions = (Condition("UpdatingVersion", FALSE, "InplaceUpgradeFailed", message),)
    update = pool_update(conditions)
    assert update is not None
    assert (update.kind, update.failed, update.progress) == ("version", True, None)
    assert degraded_node(conditions) == ("worker-2", "disk full on /var")


def test_older_operators_name_the_degraded_node_on_the_machine_set() -> None:
    sets = [
        MachineSetObservation(POOL, upgrade_degraded="Node worker-1 in nodepool degraded: boom")
    ]
    assert degraded_node((), sets) == ("worker-1", "boom")
    assert degraded_node((Condition("UpdatingVersion", TRUE, "AsExpected", IN_PROGRESS),)) is None


def test_the_degraded_node_maps_to_its_machine_by_node_ref() -> None:
    degraded = "Node node-m2 in nodepool degraded: disk full"
    sets = [MachineSetObservation(POOL, node_pool=f"{NS}/{POOL}", upgrade_degraded=degraded)]
    p = pool(
        upgrade_type="InPlace",
        conditions=(Condition("UpdatingVersion", FALSE, "InplaceUpgradeFailed", degraded),),
    )
    found = nodes_by_pool(
        HOSTED, observed([p], [machine("m1"), machine("m2")], machine_sets=sets), None
    )
    nodes = {n.machine: n for n in found.node_pools[0].nodes}
    assert (nodes["m2"].state, nodes["m2"].current, nodes["m2"].activity) == (
        NodeState.FAILED,
        True,
        "disk full",
    )
    assert (nodes["m1"].state, nodes["m1"].current) == (NodeState.READY, False)


def test_problems_are_the_conditions_that_are_not_true_on_one_line() -> None:
    conditions = (
        Condition("Ready", TRUE, "AsExpected"),
        Condition(
            "AllNodesHealthy",
            FALSE,
            "NodeConditionsFailed",
            "1 of 3 machines are not healthy\n"
            "Machine m2: NodeConditionsFailed: Node condition Ready is Unknown. \n",
        ),
        Condition("AllMachinesReady", "Unknown"),
        Condition("UpdatingVersion", TRUE),
    )
    assert pool_problems(conditions) == (
        "AllMachinesReady",
        "AllNodesHealthy: NodeConditionsFailed: 1 of 3 machines are not healthy; "
        "Machine m2: NodeConditionsFailed: Node condition Ready is Unknown.",
    )


# ── Free Agents and why a Machine waits ──────────────────────────────────────


@pytest.mark.parametrize(
    ("a", "why"),
    [
        (agent("a"), None),
        (agent("a", taken_by="m9"), "bound"),
        (
            agent("a", conditions=(Condition("Connected", TRUE), Condition("Validated", TRUE))),
            "bound",
        ),
        (agent("a", approved=False), "not approved"),
        (
            agent(
                "a",
                conditions=(
                    Condition("Bound", FALSE),
                    Condition("Connected", FALSE),
                    Condition("Validated", TRUE),
                ),
            ),
            "not connected",
        ),
        (
            agent(
                "a",
                conditions=(
                    Condition("Bound", FALSE),
                    Condition("Connected", TRUE),
                    Condition("Validated", FALSE),
                ),
            ),
            "not validated",
        ),
    ],
)
def test_an_agent_is_free_by_the_providers_rule(a: AgentObservation, why: str | None) -> None:
    assert why_not_free(a) == why


def test_free_agents_count_only_those_the_selector_matches() -> None:
    agents = [
        agent("a1"),
        agent("a2", taken_by="m1"),
        agent("a3", taken_by="m2"),
        agent("a4", approved=False),
        dataclasses.replace(agent("a5"), labels={INFRA_ENV: "hp"}),
    ]
    assert free_agents(pool(), agents) == FreeAgents(
        matching=4, free=1, not_free=(("bound", 2), ("not approved", 1))
    )
    assert free_agents(pool(agent_selector=None), agents) == FreeAgents(
        5, 2, (("bound", 2), ("not approved", 1))
    )
    assert free_agents(pool(), None) is None


def test_waiting_for_says_why_no_agent_is_reserved() -> None:
    am = agent_machine("m")
    say = lambda free, p=None: waiting_for(am, free, p or pool())  # noqa: E731
    assert waiting_for(None, None, pool()) == "Its AgentMachine does not exist yet"
    assert (
        say(None)
        == "No Agent is reserved for it (NoSuitableAgents); the Agents could not be counted"
    )
    assert say(FreeAgents(0, 0)) == f"No Agent matches this NodePool's selector ({INFRA_ENV}=dell)"
    assert (
        say(FreeAgents(0, 0), pool(agent_selector=None))
        == "There is no Agent in the cluster's agent namespace"
    )
    assert say(FreeAgents(4, 0, (("bound", 3), ("not approved", 1)))) == (
        "No free Agent matches this NodePool: 4 Agents match its selector, "
        "none is free (3 bound, 1 not approved)"
    )
    assert say(FreeAgents(1, 0, (("bound", 1),))) == (
        "No free Agent matches this NodePool: 1 Agent matches its selector, none is free (1 bound)"
    )
    assert say(FreeAgents(3, 1)) == "Waiting for the Agent provider to reserve the 1 free Agent"
    assert (
        say(FreeAgents(3, 2))
        == "Waiting for the Agent provider to reserve one of the 2 free Agents"
    )
    not_yet = agent_machine(
        "m",
        conditions=(
            Condition("AgentReserved", FALSE, "AgentNotYetFound", "agents.x is forbidden."),
        ),
    )
    assert (
        waiting_for(not_yet, FreeAgents(0, 0), pool())
        == "No Agent reserved yet: agents.x is forbidden"
    )


def test_a_waiting_node_in_the_view_says_why() -> None:
    m = machine("m", provider_id=None, node_name=None)
    agents = [agent("a1", taken_by="other"), agent("a2", approved=False)]
    found = nodes_by_pool(
        HOSTED, observed([pool(replicas=1)], [m], [agent_machine("m")], agents), None
    )
    view = found.node_pools[0]
    assert view.free_agents == FreeAgents(2, 0, (("bound", 1), ("not approved", 1)))
    (node,) = view.nodes
    assert node.waiting_for == (
        "No free Agent matches this NodePool: 2 Agents match its selector, "
        "none is free (1 bound, 1 not approved)"
    )


def test_missing_rows_stand_for_the_machines_the_pool_wants_and_has_not() -> None:
    machines = [machine("m1"), machine("m2", deleting=True)]
    rows = missing_nodes(3, machines)
    assert [r.state for r in rows] == [NodeState.MISSING, NodeState.MISSING]
    assert (
        rows[0].waiting_for
        == "The NodePool wants 3 nodes and has 1 Machine; 2 are still to be created"
    )
    assert missing_nodes(2, [machine("m1")])[0].waiting_for == (
        "The NodePool wants 2 nodes and has 1 Machine; one is still to be created"
    )
    assert missing_nodes(1, machines) == []
    assert missing_nodes(None, []) == []


def test_an_autoscaling_pool_wants_no_fixed_number_and_has_no_missing_rows() -> None:
    p = pool(replicas=None, autoscaling=Autoscaling(min=1, max=5))
    view = nodes_by_pool(HOSTED, observed([p]), None).node_pools[0]
    assert (view.wanted, view.autoscaling, view.nodes) == (None, Autoscaling(1, 5), ())


def test_wanted_and_ready_are_integers_when_unset() -> None:
    view = nodes_by_pool(
        HOSTED, observed([pool(replicas=None, current_replicas=0)]), None
    ).node_pools[0]
    assert (view.wanted, view.ready) == (0, 0)


def test_the_pool_view_carries_its_fields() -> None:
    p = pool(
        conditions=(
            Condition(
                "UpdatingVersion",
                TRUE,
                "AsExpected",
                "Updating version in progress. Target version: 4.18.30",
            ),
        )
    )
    view = nodes_by_pool(HOSTED, observed([p]), None).node_pools[0]
    assert (view.version, view.upgrade_type, view.agent_selector) == (
        "4.18.22",
        "Replace",
        f"{INFRA_ENV}=dell",
    )
    assert view.update == PoolUpdate(
        "version", "Updating version in progress. Target version: 4.18.30"
    )


# ── Agent -> server ──────────────────────────────────────────────────────────


def test_the_server_is_found_by_bare_metal_host_ignoring_case() -> None:
    row = server("ocp-dell-DL1")
    assert ServerFinder([row]).find(agent("a", bmh="ocp-dell-dl1")) == row


def test_a_name_several_servers_share_is_settled_by_mac_or_serial_or_not_at_all() -> None:
    one = server("ocp-twin", id="srv_1", macs=("02:00:00:00:00:01",), serial="S1")
    two = server("ocp-twin", id="srv_2", macs=("02:00:00:00:00:02",), serial="S2")
    finder = ServerFinder([one, two])
    assert finder.find(agent("a", bmh="ocp-twin", macs=("02:00:00:00:00:02",))) == two
    assert finder.find(agent("a", bmh="ocp-twin", serial="s1")) == one
    assert finder.find(agent("a", bmh="ocp-twin")) is None


def test_without_a_host_label_the_mac_then_the_serial_find_the_server() -> None:
    row = server("ocp-dell-DL1", macs=("02:00:00:00:00:0a",), serial="DL1")
    finder = ServerFinder([row, server("ocp-other", serial="DL2")])
    assert finder.find(agent("a", macs=("02:00:00:00:00:0A",))) == row
    assert finder.find(agent("a", serial="dl1")) == row
    assert finder.find(agent("a")) is None
    assert ServerFinder([]).find(agent("a", bmh="ocp-dell-dl1")) is None


def test_a_host_label_server_scan_does_not_know_falls_back_to_the_mac() -> None:
    row = server("ocp-renamed", macs=("02:00:00:00:00:0b",))
    assert (
        ServerFinder([row]).find(agent("a", bmh="ocp-old-name", macs=("02:00:00:00:00:0b",))) == row
    )
