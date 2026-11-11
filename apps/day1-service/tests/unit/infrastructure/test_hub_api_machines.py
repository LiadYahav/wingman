"""HttpHubApi's reads for the nodes view: Machines, MachineSets, AgentMachines, Agents (ADR-0038).

The shapes are upstream's: cluster.x-k8s.io/v1beta1 Machines and
MachineSets, capi-provider.agent-install.openshift.io/v1beta1 AgentMachines,
agent-install.openshift.io/v1beta1 Agents, and the NodePool and HostedCluster
fields the view adds (docs/ecosystem/notes/hypershift-node-state.md).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from prometheus_client import CollectorRegistry

from wingman_core.observability.metrics import WingmanMetrics
from wingman_day1.domain.errors import HubDeniedError, HubObjectNotFoundError, HubUnavailableError
from wingman_day1.domain.machines import (
    AgentMachineObservation,
    AgentObservation,
    MachineObservation,
    MachineSetObservation,
)
from wingman_day1.domain.selectors import LabelRequirement, LabelSelector, Operator
from wingman_day1.domain.status import Autoscaling, Condition
from wingman_day1.infrastructure.hub_api import HttpHubApi

TOKEN = "sha256~hub-token-never-shown-0002"
MCE = "ocp4-prod-mce-site1-a"
CP = "hcp-prod-lark-site1-ocp4-prod-lark-site1"
POOL_KEY = "hcp-prod-lark-site1/prod-lark-site1-dell"
IN_PROGRESS = "Nodepool update in progress. Total Nodes: 3. Upgraded: 1"
DEGRADED = "Node worker-2 in nodepool degraded: boom"

Handler = Callable[[httpx.Request], httpx.Response]

MACHINE: dict[str, Any] = {
    "metadata": {
        "name": "prod-lark-site1-dell-x7k2p",
        "namespace": CP,
        "deletionTimestamp": "2026-11-11T07:55:00Z",
        "labels": {"cluster.x-k8s.io/set-name": "prod-lark-site1-dell"},
        "annotations": {"hypershift.openshift.io/nodePool": POOL_KEY},
    },
    "spec": {
        "infrastructureRef": {"kind": "AgentMachine", "name": "prod-lark-site1-dell-x7k2p"},
        "providerID": "agent://5f0c0000-0000-0000-0000-000000000001",
    },
    "status": {
        "phase": "Deleting",
        "nodeRef": {"kind": "Node", "name": "worker-2"},
        "failureReason": None,
        "conditions": [
            {"type": "NodeHealthy", "status": "False", "severity": "Info", "reason": "Deleting"},
            {
                "type": "DrainingSucceeded",
                "status": "False",
                "reason": "Draining",
                "message": "Draining the node before deletion",
            },
        ],
        "v1beta2": {
            "conditions": [
                {
                    "type": "Deleting",
                    "status": "True",
                    "reason": "DrainingNode",
                    "message": "Drain not completed yet",
                }
            ]
        },
    },
}
MACHINE_SET: dict[str, Any] = {
    "metadata": {
        "name": "prod-lark-site1-dell-8f6bc",
        "labels": {"cluster.x-k8s.io/deployment-name": "prod-lark-site1-dell"},
        "annotations": {
            "hypershift.openshift.io/nodePool": POOL_KEY,
            "machinedeployment.clusters.x-k8s.io/revision": "3",
            "hypershift.openshift.io/nodePoolUpgradeInProgressTrue": IN_PROGRESS,
            "hypershift.openshift.io/nodePoolUpgradeInProgressFalse": DEGRADED,
        },
    }
}
AGENT_MACHINE: dict[str, Any] = {
    "metadata": {"name": "prod-lark-site1-dell-x7k2p"},
    "status": {
        "agentRef": {"namespace": "inventory", "name": "5f0c0000-0000-0000-0000-000000000001"},
        "conditions": [{"type": "AgentReserved", "status": "True", "reason": "AgentReserved"}],
    },
}
AGENT: dict[str, Any] = {
    "metadata": {
        "name": "5f0c0000-0000-0000-0000-000000000001",
        "labels": {
            "agent-install.openshift.io/bmh": "ocp-dell-r660-site1-64c-512gb-dl0000123",
            "agentMachineRef": "prod-lark-site1-dell-x7k2p",
            "infraenvs.agent-install.openshift.io": "dell-r660-site1",
        },
    },
    "spec": {"approved": True, "clusterDeploymentName": {"name": "ocp4-prod-lark-site1"}},
    "status": {
        "debugInfo": {"state": "installing-in-progress", "stateInfo": "Host is installing"},
        "progress": {"currentStage": "Writing image to disk"},
        "inventory": {
            "hostname": "worker-2",
            "systemVendor": {"serialNumber": "DL0000123", "manufacturer": "Dell Inc."},
            "interfaces": [{"macAddress": "02:00:00:00:00:0A"}, {"name": "lo"}],
        },
        "conditions": [
            {"type": "Bound", "status": "True"},
            {"type": "Installed", "status": "False"},
        ],
    },
}


class Recorder:
    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def reply(status: int, body: object = None) -> Handler:
    return lambda _request: httpx.Response(status, json=body)


def listing(*items: object) -> Handler:
    return reply(200, {"apiVersion": "v1", "kind": "List", "items": list(items)})


def make(handler: Handler, *, metrics: WingmanMetrics | None = None) -> tuple[HttpHubApi, Recorder]:
    recorder = Recorder(handler)
    api = HttpHubApi(
        tokens={MCE: TOKEN},
        domain="hubs.example.invalid",
        verify=False,
        timeout_seconds=2.0,
        metrics=metrics,
        transport=httpx.MockTransport(recorder),
        timer=iter(range(1000)).__next__,
    )
    return api, recorder


async def test_machines_are_read_as_v1beta1_in_the_control_plane_namespace() -> None:
    other = {**MACHINE, "metadata": {"name": "aa-first"}}
    api, recorder = make(listing(MACHINE, other))
    first, machine = await api.machines(MCE, namespace=CP)
    assert first.name == "aa-first"
    assert machine == MachineObservation(
        name="prod-lark-site1-dell-x7k2p",
        node_pool=POOL_KEY,
        machine_set="prod-lark-site1-dell",
        infrastructure_ref="prod-lark-site1-dell-x7k2p",
        provider_id="agent://5f0c0000-0000-0000-0000-000000000001",
        phase="Deleting",
        node_name="worker-2",
        deleting=True,
        conditions=(
            Condition("NodeHealthy", "False", "Deleting"),
            Condition(
                "DrainingSucceeded", "False", "Draining", "Draining the node before deletion"
            ),
        ),
        v1beta2_conditions=(
            Condition("Deleting", "True", "DrainingNode", "Drain not completed yet"),
        ),
    )
    assert machine.agent_name == "5f0c0000-0000-0000-0000-000000000001"
    request = recorder.requests[0]
    assert request.url.path == f"/apis/cluster.x-k8s.io/v1beta1/namespaces/{CP}/machines"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"


async def test_machine_sets_carry_their_revision_and_in_place_annotations() -> None:
    api, recorder = make(listing(MACHINE_SET))
    assert await api.machine_sets(MCE, namespace=CP) == [
        MachineSetObservation(
            name="prod-lark-site1-dell-8f6bc",
            node_pool=POOL_KEY,
            deployment="prod-lark-site1-dell",
            revision=3,
            upgrade_in_progress=IN_PROGRESS,
            upgrade_degraded=DEGRADED,
        )
    ]
    assert recorder.requests[0].url.path.endswith(f"/namespaces/{CP}/machinesets")


async def test_agent_machines_name_the_agent_they_reserved() -> None:
    api, recorder = make(listing(AGENT_MACHINE, {"metadata": {"name": "waiting"}}))
    assert await api.agent_machines(MCE, namespace=CP) == [
        AgentMachineObservation(
            name="prod-lark-site1-dell-x7k2p",
            agent_name="5f0c0000-0000-0000-0000-000000000001",
            conditions=(Condition("AgentReserved", "True", "AgentReserved"),),
        ),
        AgentMachineObservation(name="waiting"),
    ]
    assert recorder.requests[0].url.path == (
        f"/apis/capi-provider.agent-install.openshift.io/v1beta1/namespaces/{CP}/agentmachines"
    )


async def test_agents_carry_their_host_label_stage_serial_and_macs() -> None:
    bare = {"metadata": {"name": "bare"}, "spec": {"hostname": "h1"}}
    api, recorder = make(listing(AGENT, bare))
    agent, other = await api.agents(MCE, namespace="inventory")
    assert agent == AgentObservation(
        name="5f0c0000-0000-0000-0000-000000000001",
        labels=AGENT["metadata"]["labels"],
        approved=True,
        hostname="worker-2",
        state="installing-in-progress",
        stage="Writing image to disk",
        serial="DL0000123",
        macs=("02:00:00:00:00:0a",),
        conditions=(Condition("Bound", "True"), Condition("Installed", "False")),
    )
    assert (agent.bmh, agent.taken_by) == (
        "ocp-dell-r660-site1-64c-512gb-dl0000123",
        "prod-lark-site1-dell-x7k2p",
    )
    assert other == AgentObservation(name="bare", hostname="h1")
    assert recorder.requests[0].url.path == (
        "/apis/agent-install.openshift.io/v1beta1/namespaces/inventory/agents"
    )


async def test_node_pools_carry_the_fields_the_nodes_view_reads() -> None:
    pool = {
        "metadata": {"name": "prod-lark-site1-dell"},
        "spec": {
            "autoScaling": {"min": 1, "max": 5},
            "management": {"upgradeType": "InPlace"},
            "platform": {
                "type": "Agent",
                "agent": {
                    "agentLabelSelector": {
                        "matchLabels": {"infraenvs.agent-install.openshift.io": "dell"},
                        "matchExpressions": [
                            {"key": "zone", "operator": "In", "values": ["a", "b"]},
                            {"key": "retired", "operator": "DoesNotExist"},
                        ],
                    }
                },
            },
        },
        "status": {"replicas": 2, "version": "4.18.22"},
    }
    api, _ = make(listing(pool))
    (found,) = await api.node_pools(MCE, namespace="hcp-prod-lark-site1")
    assert (found.replicas, found.desired_replicas, found.current_replicas) == (None, 2, 2)
    assert (found.autoscaling, found.upgrade_type, found.version) == (
        Autoscaling(1, 5),
        "InPlace",
        "4.18.22",
    )
    assert found.agent_selector == LabelSelector(
        match_labels=(("infraenvs.agent-install.openshift.io", "dell"),),
        match_expressions=(
            LabelRequirement("zone", Operator.IN, ("a", "b")),
            LabelRequirement("retired", Operator.DOES_NOT_EXIST),
        ),
    )


async def test_a_hosted_cluster_names_its_agent_namespace() -> None:
    hosted = {
        "metadata": {"name": "ocp4-prod-lark-site1"},
        "spec": {"platform": {"type": "Agent", "agent": {"agentNamespace": "inventory"}}},
    }
    api, _ = make(reply(200, hosted))
    found = await api.hosted_cluster(
        MCE, namespace="hcp-prod-lark-site1", name="ocp4-prod-lark-site1"
    )
    assert found.agent_namespace == "inventory"


ListCall = Callable[[HttpHubApi], Any]
CALLS: dict[str, ListCall] = {
    "machines": lambda api: api.machines(MCE, namespace=CP),
    "machine_sets": lambda api: api.machine_sets(MCE, namespace=CP),
    "agent_machines": lambda api: api.agent_machines(MCE, namespace=CP),
    "agents": lambda api: api.agents(MCE, namespace="inventory"),
}


@pytest.mark.parametrize("call", sorted(CALLS))
async def test_a_list_the_hub_does_not_serve_is_unavailable_not_a_missing_cluster(
    call: str,
) -> None:
    api, _ = make(reply(404, {"kind": "Status", "reason": "NotFound"}))
    with pytest.raises(HubUnavailableError, match="does not serve"):
        await CALLS[call](api)


@pytest.mark.parametrize("call", sorted(CALLS))
async def test_a_list_the_token_may_not_read_is_denied_and_names_the_path(call: str) -> None:
    api, _ = make(reply(403, {"kind": "Status", "reason": "Forbidden"}))
    with pytest.raises(HubDeniedError, match=r"\(403\) on GET /apis/") as caught:
        await CALLS[call](api)
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize(
    ("call", "item"),
    [
        ("machines", {"metadata": {}}),
        ("machines", {**MACHINE, "status": {"conditions": "nope"}}),
        (
            "machine_sets",
            {
                "metadata": {
                    "name": "x",
                    "annotations": {"machinedeployment.clusters.x-k8s.io/revision": "three"},
                }
            },
        ),
        ("agent_machines", {"metadata": {"name": "x"}, "status": {"agentRef": "nope"}}),
        ("agents", {"metadata": {"name": "x", "labels": {"a": 1}}}),
        ("agents", {"metadata": {"name": "x"}, "status": {"inventory": {"interfaces": "nope"}}}),
    ],
)
async def test_malformed_objects_are_unavailable(call: str, item: object) -> None:
    api, _ = make(listing(item))
    with pytest.raises(HubUnavailableError, match="malformed"):
        await CALLS[call](api)


async def test_an_unknown_selector_operator_makes_the_node_pool_list_malformed() -> None:
    pool = {
        "metadata": {"name": "p"},
        "spec": {
            "platform": {
                "agent": {
                    "agentLabelSelector": {"matchExpressions": [{"key": "k", "operator": "Like"}]}
                }
            }
        },
    }
    api, _ = make(listing(pool))
    with pytest.raises(HubUnavailableError, match="malformed"):
        await api.node_pools(MCE, namespace="hcp-prod-lark-site1")


async def test_a_namespace_that_cannot_exist_never_reaches_the_hub() -> None:
    api, recorder = make(listing())
    with pytest.raises(HubObjectNotFoundError):
        await api.machines(MCE, namespace="../secrets")
    assert recorder.requests == []


async def test_the_new_reads_are_counted_under_their_operations() -> None:
    metrics = WingmanMetrics(CollectorRegistry(), component="day1", version="t", commit="t")
    api, _ = make(listing(), metrics=metrics)
    for call in CALLS.values():
        await call(api)
    denied, _ = make(reply(403, {}), metrics=metrics)
    with pytest.raises(HubDeniedError):
        await denied.agents(MCE, namespace="inventory")

    def count(operation: str, outcome: str) -> float | None:
        labels = {"dependency": "kubernetes", "operation": operation, "outcome": outcome}
        return metrics.registry.get_sample_value("wingman_dependency_requests_total", labels)

    assert [
        count(op, "ok")
        for op in ("list_machines", "list_machine_sets", "list_agent_machines", "list_agents")
    ] == [1.0] * 4
    assert count("list_agents", "denied") == 1.0
