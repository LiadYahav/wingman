"""The fake MCE hubs for ``DAY1_FAKE_FLEET``, built from ``dev/fleet-fixtures/mce.yaml``.

Each scenario in the fixture becomes the objects a real MCE serves for a
hosted cluster: its HostedCluster and NodePools, and in its control-plane
namespace the MachineSets, Machines and AgentMachines, with the Agents in its
agent namespace. They are built as Kubernetes JSON and read with
``HttpHubApi``'s own parsers, so the fake cannot drift from what the adapter
understands. Agents carry the servers' serials and MACs from the fake
server-scan fleet, and their BareMetalHost label is the server's name,
lowercased as a Kubernetes name is.

Each hub's own nodes and pods (``hubs:``, for MCE placement's free pods,
ADR-0050) are built as Node objects and a pod Table, read with the
adapter's parsers too. An MCE that is neither in ``hubs`` nor hosts a
fixture cluster is not configured, so placement never picks it.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import yaml

from wingman_day1.domain.machines import (
    AGENT_MACHINE_REF_LABEL,
    BMH_LABEL,
    DEPLOYMENT_NAME_LABEL,
    INFRA_ENV_LABEL,
    NODE_POOL_ANNOTATION,
    PROVIDER_ID_PREFIX,
    REVISION_ANNOTATION,
    SET_NAME_LABEL,
    UPGRADE_IN_PROGRESS_ANNOTATION,
    AgentMachineObservation,
    AgentObservation,
    MachineObservation,
    MachineSetObservation,
)
from wingman_day1.domain.mce_capacity import NodeObservation
from wingman_day1.domain.names import HostedClusterNaming, HostedClusterRef
from wingman_day1.domain.servers import ServerRow
from wingman_day1.domain.status import HostedClusterObservation, NodePoolObservation
from wingman_day1.infrastructure.fake_hub import FakeHubApi
from wingman_day1.infrastructure.hub_api import (
    agent_from,
    agent_machine_from,
    hosted_cluster_from,
    machine_from,
    machine_set_from,
    node_from,
    node_pool_from,
    pods_per_node_from,
)

JSON = dict[str, Any]
MCE_FILE: Final = Path("dev/fleet-fixtures/mce.yaml")
DELETING_SINCE: Final = "2026-11-11T07:55:00Z"
SCENARIOS: Final = frozenset({"ready", "rebooting", "waiting", "installing", "deleting"})
_NOT_READY_REASON: Final = {
    "waiting": "NoSuitableAgents",
    "installing": "InstallationInProgress",
    "deleting": "Deleting",
}
_UNHEALTHY_REASON: Final = {
    "rebooting": "NodeConditionsFailed: Node condition Ready is Unknown.",
    "waiting": "WaitingForNodeRef",
    "installing": "WaitingForNodeRef",
}


def default_mce_file() -> Path:
    """``dev/fleet-fixtures/mce.yaml`` of this checkout."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / MCE_FILE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{MCE_FILE} not found above this file")


def load_fake_mce(
    path: Path, *, servers: Iterable[ServerRow], naming: HostedClusterNaming
) -> FakeHubApi:
    """The fake MCE hubs the fixture at ``path`` describes, for these servers and naming."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("clusters"), list):
        raise TypeError(f"{path}: expected a mapping with a 'clusters' list")
    builder = _Builder(servers, naming=naming, agent_namespace=str(raw["agent_namespace"]))
    for cluster in raw["clusters"]:
        builder.cluster(cluster)
    for mce, nodes in (raw.get("hubs") or {}).items():
        builder.hub_nodes(str(mce), nodes)
    return builder.hub()


def _short(text: str) -> str:
    """Five stable lowercase characters, like the random suffixes CAPI gives names."""
    return hashlib.sha256(text.encode()).hexdigest()[:5]


def _node_object(raw: Mapping[str, Any]) -> JSON:
    """A Node as the API server serves it: its role labels, cordon, Ready and allocatable pods."""
    role = str(raw.get("role", "worker"))
    roles = ("master", "control-plane") if role == "control-plane" else (role,)
    ready = bool(raw.get("ready", True))
    spec: JSON = {"unschedulable": True} if raw.get("cordoned") else {}
    if raw.get("tainted") or role == "infra":
        spec["taints"] = [{"key": "node-role.kubernetes.io/infra", "effect": "NoSchedule"}]
    return {
        "metadata": {
            "name": str(raw["name"]),
            "labels": {f"node-role.kubernetes.io/{r}": "" for r in roles},
        },
        "spec": spec,
        "status": {
            "allocatable": {"pods": str(raw.get("allocatable", 250))},
            "conditions": [
                _condition("Ready", ready, "KubeletReady" if ready else "NodeStatusUnknown")
            ],
        },
    }


def _pod_table(nodes: Sequence[Mapping[str, Any]]) -> JSON:
    """The hub's non-terminal pods as a Table: ``pods`` rows per node, plus one not bound yet."""
    columns = ("Name", "Ready", "Status", "Restarts", "Age", "IP", "Node")
    rows = [
        {
            "cells": [
                f"{node['name']}-pod-{i}",
                "1/1",
                "Running",
                "0",
                "9d",
                "10.128.0.2",
                str(node["name"]),
            ]
        }
        for node in nodes
        for i in range(int(node.get("pods", 0)))
    ]
    rows.append({"cells": ["pending-0", "0/1", "Pending", "0", "1m", "<none>", "<none>"]})
    return {
        "kind": "Table",
        "apiVersion": "meta.k8s.io/v1",
        "metadata": {"continue": ""},
        "columnDefinitions": [{"name": name, "type": "string"} for name in columns],
        "rows": rows,
    }


def _condition(kind: str, status: bool, reason: str = "", message: str = "") -> JSON:
    return {
        "type": kind,
        "status": "True" if status else "False",
        "reason": reason,
        "message": message,
    }


class _Builder:
    """Turns scenarios into the Kubernetes objects an MCE would serve, and parses them."""

    def __init__(
        self, servers: Iterable[ServerRow], *, naming: HostedClusterNaming, agent_namespace: str
    ) -> None:
        self._servers = {row.name.lower(): row for row in servers}
        self._naming = naming
        self._agent_ns = agent_namespace
        self._hosted: dict[str, list[HostedClusterObservation]] = defaultdict(list)
        self._pools: dict[tuple[str, str], list[NodePoolObservation]] = defaultdict(list)
        self._machines: dict[tuple[str, str], list[MachineObservation]] = defaultdict(list)
        self._sets: dict[tuple[str, str], list[MachineSetObservation]] = defaultdict(list)
        self._agent_machines: dict[tuple[str, str], list[AgentMachineObservation]] = defaultdict(
            list
        )
        self._agents: dict[tuple[str, str], list[AgentObservation]] = defaultdict(list)
        self._infra_envs: dict[str, set[str]] = defaultdict(set)
        self._nodes: dict[str, list[NodeObservation]] = {}
        self._pods: dict[str, dict[str, int]] = {}

    def hub_nodes(self, mce: str, raw: Mapping[str, Any]) -> None:
        """An MCE's own nodes, their pods and its free Agents, in the shapes the adapter reads."""
        nodes: Sequence[Mapping[str, Any]] = raw.get("nodes") or []
        self._nodes[mce] = [node_from(_node_object(node)) for node in nodes]
        self._pods[mce] = pods_per_node_from(_pod_table(nodes))
        for free in raw.get("free_agents") or []:
            server, infra_env = str(free["server"]), str(free["infra_env"])
            self._infra_envs[mce].add(infra_env)
            agent = self._agent(server, infra_env, scenario="free", taken_by=None, hostname=None)
            self._agents[(mce, self._agent_ns)].append(agent_from(agent))

    def hub(self) -> FakeHubApi:
        return FakeHubApi(
            nodes=self._nodes,
            pods=self._pods,
            hosted_clusters=self._hosted,
            node_pools=self._pools,
            infra_envs={mce: {self._agent_ns: sorted(n)} for mce, n in self._infra_envs.items()},
            machines=self._machines,
            machine_sets=self._sets,
            agent_machines=self._agent_machines,
            agents=self._agents,
        )

    def cluster(self, raw: Mapping[str, Any]) -> None:
        ref = self._naming.for_file(str(raw["name"]))
        mce = str(raw["mce"])
        hosted = {
            "metadata": {"name": ref.name, "namespace": ref.namespace},
            "spec": {"platform": {"type": "Agent", "agent": {"agentNamespace": self._agent_ns}}},
            "status": {
                "version": {"history": [{"version": str(raw["version"]), "state": "Completed"}]},
                "conditions": [
                    _condition("Available", True, "AsExpected"),
                    _condition("Degraded", False, "AsExpected"),
                    _condition("Progressing", False, "AsExpected"),
                ],
            },
        }
        self._hosted[mce].append(
            hosted_cluster_from(hosted, namespace=ref.namespace, name=ref.name)
        )
        for pool in raw.get("node_pools") or []:
            self._pool(mce, ref, pool)
        for spare in raw.get("spare_agents") or []:
            self._spare_agent(mce, spare)

    def _pool(self, mce: str, ref: HostedClusterRef, raw: Mapping[str, Any]) -> None:
        infra_env = str(raw["infra_env"])
        name = f"{ref.cluster_name}-{infra_env}"
        key = f"{ref.namespace}/{name}"
        upgrade = str(raw["upgrade"])
        nodes: Sequence[Mapping[str, Any]] = raw.get("nodes") or []
        updating: Mapping[str, Any] | None = raw.get("updating")
        progress = None
        if updating is not None and upgrade == "InPlace":
            progress = (
                f"Nodepool update in progress. Target Config version: {_short(str(updating))}. "
                f"Total Nodes: {len(nodes)}. Upgraded: {updating.get('upgraded', 0)}"
            )
        set_names = self._machine_sets(mce, ref, name, key, upgrade, nodes, progress)
        self._infra_envs[mce].add(infra_env)
        machines = [
            self._node(
                mce, ref, key, set_names[int(node.get("revision", 1))], name, infra_env, node, i
            )
            for i, node in enumerate(nodes)
        ]
        self._pools[(mce, ref.namespace)].append(
            node_pool_from(self._node_pool(ref, name, infra_env, raw, nodes, machines, progress))
        )

    def _machine_sets(
        self,
        mce: str,
        ref: HostedClusterRef,
        pool: str,
        key: str,
        upgrade: str,
        nodes: Sequence[Mapping[str, Any]],
        progress: str | None,
    ) -> dict[int, str]:
        """The pool's MachineSets by revision: one named after it (InPlace), or one per revision."""
        namespace = ref.control_plane_namespace
        revisions = sorted({int(node.get("revision", 1)) for node in nodes} | {1})
        names: dict[int, str] = {}
        for revision in revisions:
            name = pool if upgrade == "InPlace" else f"{pool}-{_short(f'{pool}/{revision}')}"
            annotations = {NODE_POOL_ANNOTATION: key}
            labels: dict[str, str] = {}
            if upgrade == "InPlace" and progress is not None:
                annotations[UPGRADE_IN_PROGRESS_ANNOTATION] = progress
            if upgrade != "InPlace":
                annotations[REVISION_ANNOTATION] = str(revision)
                labels[DEPLOYMENT_NAME_LABEL] = pool
            raw = {"metadata": {"name": name, "labels": labels, "annotations": annotations}}
            self._sets[(mce, namespace)].append(machine_set_from(raw))
            names[revision] = name
        return names

    def _node(
        self,
        mce: str,
        ref: HostedClusterRef,
        key: str,
        set_name: str,
        pool: str,
        infra_env: str,
        raw: Mapping[str, Any],
        index: int,
    ) -> str:
        """Add one node's Machine, AgentMachine and Agent; returns the Machine's name."""
        scenario = str(raw.get("as", "ready"))
        if scenario not in SCENARIOS:
            raise ValueError(f"{pool}: a node is {scenario!r}; expected one of {sorted(SCENARIOS)}")
        server = raw.get("server")
        name = f"{set_name}-{_short(str(server or f'{pool}/machine/{index}'))}"
        agent = self._agent_name(server) if server and scenario != "waiting" else None
        host = str(server).lower() if server else None
        has_node = scenario in {"ready", "rebooting", "deleting"}
        labels = {SET_NAME_LABEL: set_name}
        metadata: JSON = {
            "name": name,
            "labels": labels,
            "annotations": {NODE_POOL_ANNOTATION: key},
        }
        if set_name != pool:
            labels[DEPLOYMENT_NAME_LABEL] = pool
        if scenario == "deleting":
            metadata["deletionTimestamp"] = DELETING_SINCE
        machine = {
            "metadata": metadata,
            "spec": {
                "clusterName": ref.name,
                "infrastructureRef": {"kind": "AgentMachine", "name": name},
                **({"providerID": f"{PROVIDER_ID_PREFIX}{agent}"} if agent else {}),
            },
            "status": {
                "phase": {
                    "ready": "Running",
                    "rebooting": "Running",
                    "waiting": "Pending",
                    "installing": "Provisioned",
                    "deleting": "Deleting",
                }[scenario],
                **({"nodeRef": {"kind": "Node", "name": host}} if has_node else {}),
                "conditions": _machine_conditions(scenario),
            },
        }
        namespace = ref.control_plane_namespace
        self._machines[(mce, namespace)].append(machine_from(machine))
        self._agent_machines[(mce, namespace)].append(
            agent_machine_from(_agent_machine(name, agent, scenario, self._agent_ns))
        )
        if agent is not None and server is not None:
            raw_agent = self._agent(
                str(server), infra_env, scenario=scenario, taken_by=name, hostname=host
            )
            self._agents[(mce, self._agent_ns)].append(agent_from(raw_agent))
        return name

    def _spare_agent(self, mce: str, raw: Mapping[str, Any]) -> None:
        server, scenario = str(raw["server"]), str(raw["as"])
        if scenario not in {"bound", "unapproved"}:
            raise ValueError(f"spare Agent {server}: {scenario!r} is neither bound nor unapproved")
        infra_env = str(raw["infra_env"])
        self._infra_envs[mce].add(infra_env)
        taken_by = f"{infra_env}-gone" if scenario == "bound" else None
        agent = self._agent(server, infra_env, scenario=scenario, taken_by=taken_by, hostname=None)
        self._agents[(mce, self._agent_ns)].append(agent_from(agent))

    def _agent_name(self, server: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"fake-agent/{server.lower()}"))

    def _agent(
        self,
        server: str,
        infra_env: str,
        *,
        scenario: str,
        taken_by: str | None,
        hostname: str | None,
    ) -> JSON:
        row = self._servers.get(server.lower())
        if row is None:
            raise ValueError(f"an Agent names {server!r}, which servers.yaml does not have")
        labels = {BMH_LABEL: server.lower(), INFRA_ENV_LABEL: infra_env}
        if taken_by is not None:
            labels[AGENT_MACHINE_REF_LABEL] = taken_by
        installing = scenario == "installing"
        installed = scenario in {"ready", "rebooting", "deleting"}
        state, stage = {
            "installing": ("installing-in-progress", "Writing image to disk"),
            "bound": ("unbinding-pending-user-action", None),
            "unapproved": ("known-unbound", None),
            "free": ("known-unbound", None),
        }.get(scenario, ("added-to-existing-cluster", "Done"))
        return {
            "metadata": {"name": self._agent_name(server), "labels": labels},
            "spec": {"approved": scenario != "unapproved", "hostname": hostname or server.lower()},
            "status": {
                "debugInfo": {"state": state},
                **({"progress": {"currentStage": stage}} if stage else {}),
                "inventory": {
                    "hostname": server.lower(),
                    "systemVendor": {"serialNumber": row.serial, "manufacturer": row.vendor},
                    "interfaces": [{"macAddress": mac} for mac in row.macs],
                },
                "conditions": [
                    _condition("Connected", True, "AgentIsConnected"),
                    _condition("Validated", True, "ValidationsPassing"),
                    _condition("Bound", scenario not in {"unapproved", "free"}, "Bound"),
                    _condition(
                        "Installed",
                        installed,
                        "InstallationInProgress" if installing else "InstallationCompleted",
                    ),
                ],
            },
        }

    def _node_pool(
        self,
        ref: HostedClusterRef,
        name: str,
        infra_env: str,
        raw: Mapping[str, Any],
        nodes: Sequence[Mapping[str, Any]],
        machines: Sequence[str],
        progress: str | None,
    ) -> JSON:
        scenarios = [str(node.get("as", "ready")) for node in nodes]
        updating: Mapping[str, Any] | None = raw.get("updating")
        kind = updating.get("kind") if updating else None
        message = progress
        if updating is not None and progress is None:
            message = f"Updating {kind} in progress. Target {kind}: {updating.get('target')}"
        return {
            "metadata": {"name": name, "namespace": ref.namespace},
            "spec": {
                "clusterName": ref.name,
                "replicas": int(raw["replicas"]),
                "management": {"upgradeType": str(raw["upgrade"])},
                "platform": {
                    "type": "Agent",
                    "agent": {"agentLabelSelector": {"matchLabels": {INFRA_ENV_LABEL: infra_env}}},
                },
            },
            "status": {
                "replicas": scenarios.count("ready"),
                "version": str(raw["version"]),
                "conditions": [
                    _condition("Ready", True, "AsExpected"),
                    _aggregate("AllMachinesReady", "ready", machines, scenarios, _NOT_READY_REASON),
                    _aggregate(
                        "AllNodesHealthy", "healthy", machines, scenarios, _UNHEALTHY_REASON
                    ),
                    _condition("UpdatingVersion", kind == "version", "AsExpected", message or "")
                    if kind == "version"
                    else _condition("UpdatingVersion", False, "AsExpected"),
                    _condition("UpdatingConfig", kind == "config", "AsExpected", message or "")
                    if kind == "config"
                    else _condition("UpdatingConfig", False, "AsExpected"),
                ],
            },
        }


def _aggregate(
    kind: str,
    adjective: str,
    machines: Sequence[str],
    scenarios: Sequence[str],
    reasons: Mapping[str, str],
) -> JSON:
    """A NodePool condition over its Machines, worded as HyperShift's aggregator words it."""
    bad = [(m, reasons[s]) for m, s in zip(machines, scenarios, strict=True) if s in reasons]
    if not bad:
        return _condition(kind, True, "AsExpected", "All is well")
    lines = "".join(f"Machine {machine}: {reason}\n" for machine, reason in bad)
    message = f"{len(bad)} of {len(machines)} machines are not {adjective}\n{lines}"
    reason = ",".join(sorted({reason.split(":", 1)[0] for _, reason in bad}))
    return _condition(kind, False, reason, message)


def _machine_conditions(scenario: str) -> list[JSON]:
    if scenario == "waiting":
        return [
            _condition("Ready", False, "NoSuitableAgents", "0 of 5 completed"),
            _condition("InfrastructureReady", False, "NoSuitableAgents", "0 of 5 completed"),
            _condition("NodeHealthy", False, "WaitingForNodeRef"),
        ]
    if scenario == "installing":
        return [
            _condition("Ready", False, "InstallationInProgress", "3 of 5 completed"),
            _condition("InfrastructureReady", False, "InstallationInProgress", "3 of 5 completed"),
            _condition("NodeHealthy", False, "WaitingForNodeRef"),
        ]
    conditions = [
        _condition(
            "Ready",
            scenario != "rebooting",
            "NodeConditionsFailed" if scenario == "rebooting" else "",
        ),
        _condition("InfrastructureReady", True),
        _condition(
            "NodeHealthy",
            scenario != "rebooting",
            "NodeConditionsFailed" if scenario == "rebooting" else "",
            "Node condition Ready is Unknown. " if scenario == "rebooting" else "",
        ),
    ]
    if scenario == "deleting":
        conditions += [
            _condition("PreDrainDeleteHookSucceeded", True),
            _condition("DrainingSucceeded", False, "Draining", "Draining the node before deletion"),
        ]
    return conditions


def _agent_machine(name: str, agent: str | None, scenario: str, agent_ns: str) -> JSON:
    if agent is None:
        not_yet = [
            _condition(kind, False, "AgentNotYetFound", "Agent not yet reserved")
            for kind in ("AgentSpecSynced", "AgentValidated", "AgentRequirementsMet", "Installed")
        ]
        return {
            "metadata": {"name": name},
            "status": {
                "conditions": [_condition("AgentReserved", False, "NoSuitableAgents"), *not_yet]
            },
        }
    installed = scenario != "installing"
    return {
        "metadata": {"name": name},
        "spec": {"providerID": f"{PROVIDER_ID_PREFIX}{agent}"},
        "status": {
            "agentRef": {"namespace": agent_ns, "name": agent},
            "conditions": [
                _condition("AgentReserved", True),
                _condition("AgentSpecSynced", True),
                _condition("AgentValidated", True),
                _condition("AgentRequirementsMet", True),
                _condition(
                    "Installed",
                    installed,
                    "" if installed else "InstallationInProgress",
                    "" if installed else "The installation is in progress: Writing image to disk",
                ),
            ],
        },
    }
