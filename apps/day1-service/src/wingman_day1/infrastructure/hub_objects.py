"""An MCE hub's Kubernetes objects, parsed into day1's domain types (``HttpHubApi``'s reads).

Each parser takes one object (or one list page) as the API server sends it
and raises ``KeyError``, ``TypeError`` or ``ValueError`` when it is
malformed; the adapter turns those into ``HubUnavailableError`` naming the
path, never the token.
"""

from __future__ import annotations

import re
from typing import Final

from wingman_day1.domain.herzi_marks import herzi_marks
from wingman_day1.domain.infra_env_pools import InfraEnvObservation
from wingman_day1.domain.machines import (
    DEPLOYMENT_NAME_LABEL,
    NODE_POOL_ANNOTATION,
    REVISION_ANNOTATION,
    SET_NAME_LABEL,
    UPGRADE_DEGRADED_ANNOTATION,
    UPGRADE_IN_PROGRESS_ANNOTATION,
    AgentMachineObservation,
    AgentObservation,
    MachineObservation,
    MachineSetObservation,
)
from wingman_day1.domain.mce_capacity import (
    BLOCKING_TAINTS,
    CONTROL_PLANE_ROLES,
    INFRA_ROLE,
    NodeObservation,
)
from wingman_day1.domain.selectors import LabelRequirement, LabelSelector, Operator
from wingman_day1.domain.status import (
    Autoscaling,
    Condition,
    HostedClusterObservation,
    NodePoolObservation,
)
from wingman_day1.infrastructure.http import JSON

NO_NODE: Final = "<none>"
"""The Table's Node cell of a pod not bound to a node yet."""
_QUANTITY = re.compile(r"^([0-9]+)(k|M)?$")
_QUANTITY_SCALE: Final = {None: 1, "k": 1000, "M": 1_000_000}


def _mapping(value: JSON) -> dict[str, JSON]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"expected an object, got {type(value).__name__}")
    return value


def list_items(raw: JSON) -> list[JSON]:
    """A list's ``items``; none when it has none."""
    items = _mapping(raw).get("items") or []
    if not isinstance(items, list):
        raise TypeError("items is not a list")
    return items


def _metadata_name(raw: JSON) -> str:
    name = _mapping(_mapping(raw)["metadata"])["name"]
    if not isinstance(name, str) or not name:
        raise ValueError("metadata.name is missing")
    return name


def _text(value: JSON) -> str | None:
    return value if isinstance(value, str) and value else None


def _replicas(value: JSON) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"replicas {value!r} is not a non-negative integer")
    return value


def _conditions(status: dict[str, JSON]) -> tuple[Condition, ...]:
    raw = status.get("conditions") or []
    if not isinstance(raw, list):
        raise TypeError("status.conditions is not a list")
    conditions: list[Condition] = []
    for item in raw:
        condition = _mapping(item)
        conditions.append(
            Condition(
                type=str(condition["type"]),
                status=str(condition.get("status", "")),
                reason=str(condition.get("reason") or ""),
                message=str(condition.get("message") or ""),
            )
        )
    return tuple(conditions)


def _strings(value: JSON, what: str) -> dict[str, str]:
    mapping = _mapping(value)
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()):
        raise TypeError(f"{what} is not a map of strings")
    return mapping


def _metadata(raw: JSON) -> tuple[dict[str, JSON], dict[str, str], dict[str, str]]:
    """``metadata``, its labels and its annotations."""
    metadata = _mapping(_mapping(raw).get("metadata"))
    return (
        metadata,
        _strings(metadata.get("labels"), "metadata.labels"),
        _strings(metadata.get("annotations"), "metadata.annotations"),
    )


def hosted_cluster_from(raw: JSON, *, namespace: str, name: str) -> HostedClusterObservation:
    """A HostedCluster (``hypershift.openshift.io/v1beta1``)."""
    spec = _mapping(_mapping(raw).get("spec"))
    agent = _mapping(_mapping(spec.get("platform")).get("agent"))
    status = _mapping(_mapping(raw).get("status"))
    history = _mapping(status.get("version")).get("history") or []
    if not isinstance(history, list):
        raise TypeError("status.version.history is not a list")
    version = _text(_mapping(history[0]).get("version")) if history else None
    return HostedClusterObservation(
        name=name,
        namespace=namespace,
        phase=_text(status.get("phase")),
        version=version,
        conditions=_conditions(status),
        agent_namespace=_text(agent.get("agentNamespace")),
    )


def infra_env_from(raw: JSON) -> InfraEnvObservation:
    """An InfraEnv (``agent-install.openshift.io/v1beta1``): name, agentLabels, herzi's marks."""
    _, labels, annotations = _metadata(raw)
    agent_labels = _mapping(_mapping(raw).get("spec")).get("agentLabels")
    return InfraEnvObservation(
        _metadata_name(raw),
        _strings(agent_labels, "spec.agentLabels"),
        herzi_marks(labels, annotations),
    )


def node_pool_from(raw: JSON) -> NodePoolObservation:
    """A NodePool (``hypershift.openshift.io/v1beta1``)."""
    pool = _mapping(raw)
    spec = _mapping(pool.get("spec"))
    status = _mapping(pool.get("status"))
    current = _replicas(status.get("replicas"))
    desired = _replicas(spec.get("replicas"))
    scaling = spec.get("autoScaling")
    autoscaling = None
    if scaling is not None:
        bounds = _mapping(scaling)
        autoscaling = Autoscaling(
            min=_replicas(bounds.get("min")) or 0, max=_replicas(bounds["max"]) or 0
        )
    platform = _mapping(_mapping(spec.get("platform")).get("agent"))
    return NodePoolObservation(
        name=_metadata_name(pool),
        desired_replicas=desired if desired is not None else (current or 0),
        current_replicas=current or 0,
        conditions=_conditions(status),
        replicas=desired,
        autoscaling=autoscaling,
        upgrade_type=_text(_mapping(spec.get("management")).get("upgradeType")),
        version=_text(status.get("version")),
        agent_selector=label_selector_from(platform.get("agentLabelSelector")),
    )


def label_selector_from(raw: JSON) -> LabelSelector | None:
    """A ``metav1.LabelSelector``; ``None`` when absent. An unknown operator is malformed."""
    if raw is None:
        return None
    selector = _mapping(raw)
    expressions = selector.get("matchExpressions") or []
    if not isinstance(expressions, list):
        raise TypeError("matchExpressions is not a list")
    requirements = []
    for item in expressions:
        expression = _mapping(item)
        values = expression.get("values") or []
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise TypeError("matchExpressions values is not a list of strings")
        requirements.append(
            LabelRequirement(
                key=str(expression["key"]),
                operator=Operator(expression["operator"]),
                values=tuple(values),
            )
        )
    labels = _strings(selector.get("matchLabels"), "matchLabels")
    return LabelSelector(
        match_labels=tuple(sorted(labels.items())), match_expressions=tuple(requirements)
    )


def machine_from(raw: JSON) -> MachineObservation:
    """A CAPI Machine (``cluster.x-k8s.io/v1beta1``)."""
    metadata, labels, annotations = _metadata(raw)
    spec = _mapping(_mapping(raw).get("spec"))
    status = _mapping(_mapping(raw).get("status"))
    return MachineObservation(
        name=_metadata_name(raw),
        node_pool=_text(annotations.get(NODE_POOL_ANNOTATION)),
        machine_set=_text(labels.get(SET_NAME_LABEL)),
        infrastructure_ref=_text(_mapping(spec.get("infrastructureRef")).get("name")),
        provider_id=_text(spec.get("providerID")),
        phase=_text(status.get("phase")),
        node_name=_text(_mapping(status.get("nodeRef")).get("name")),
        deleting=bool(metadata.get("deletionTimestamp")),
        failure_reason=_text(status.get("failureReason")),
        failure_message=_text(status.get("failureMessage")),
        conditions=_conditions(status),
        v1beta2_conditions=_conditions(_mapping(status.get("v1beta2"))),
    )


def machine_set_from(raw: JSON) -> MachineSetObservation:
    """A CAPI MachineSet (``cluster.x-k8s.io/v1beta1``)."""
    _, labels, annotations = _metadata(raw)
    revision = annotations.get(REVISION_ANNOTATION)
    return MachineSetObservation(
        name=_metadata_name(raw),
        node_pool=_text(annotations.get(NODE_POOL_ANNOTATION)),
        deployment=_text(labels.get(DEPLOYMENT_NAME_LABEL)),
        revision=int(revision) if revision else None,
        upgrade_in_progress=_text(annotations.get(UPGRADE_IN_PROGRESS_ANNOTATION)),
        upgrade_degraded=_text(annotations.get(UPGRADE_DEGRADED_ANNOTATION)),
    )


def agent_machine_from(raw: JSON) -> AgentMachineObservation:
    """An AgentMachine (``capi-provider.agent-install.openshift.io/v1beta1``)."""
    status = _mapping(_mapping(raw).get("status"))
    return AgentMachineObservation(
        name=_metadata_name(raw),
        agent_name=_text(_mapping(status.get("agentRef")).get("name")),
        conditions=_conditions(status),
    )


def agent_from(raw: JSON) -> AgentObservation:
    """An Agent (``agent-install.openshift.io/v1beta1``)."""
    _, labels, _ = _metadata(raw)
    spec = _mapping(_mapping(raw).get("spec"))
    status = _mapping(_mapping(raw).get("status"))
    inventory = _mapping(status.get("inventory"))
    interfaces = inventory.get("interfaces") or []
    if not isinstance(interfaces, list):
        raise TypeError("status.inventory.interfaces is not a list")
    macs = [_text(_mapping(item).get("macAddress")) for item in interfaces]
    return AgentObservation(
        name=_metadata_name(raw),
        labels=labels,
        approved=spec.get("approved") is True,
        hostname=_text(spec.get("hostname")) or _text(inventory.get("hostname")),
        state=_text(_mapping(status.get("debugInfo")).get("state")),
        stage=_text(_mapping(status.get("progress")).get("currentStage")),
        serial=_text(_mapping(inventory.get("systemVendor")).get("serialNumber")),
        macs=tuple(mac.lower() for mac in macs if mac),
        conditions=_conditions(status),
    )


def continue_token(raw: JSON) -> str | None:
    """A list's ``metadata.continue``: the next page's token, ``None`` on the last page."""
    token = _mapping(_mapping(raw).get("metadata")).get("continue")
    if token is not None and not isinstance(token, str):
        raise TypeError("metadata.continue is not a string")
    return token or None


def pod_quantity(value: JSON) -> int:
    """``status.allocatable.pods``: a whole number, as a Kubernetes quantity (``250``, ``1k``)."""
    if value is None:
        return 0
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if not isinstance(value, str):
        raise TypeError(f"allocatable pods {value!r} is not a quantity")
    match = _QUANTITY.match(value.strip())
    if match is None:
        raise ValueError(f"allocatable pods {value!r} is not a whole number")
    return int(match[1]) * _QUANTITY_SCALE[match[2]]


def node_from(raw: JSON) -> NodeObservation:
    """A Node (``v1``): Ready, cordoned, its roles and blocking taints, its allocatable pods."""
    _, labels, _ = _metadata(raw)
    spec = _mapping(_mapping(raw).get("spec"))
    status = _mapping(_mapping(raw).get("status"))
    taints = spec.get("taints") or []
    if not isinstance(taints, list):
        raise TypeError("spec.taints is not a list")
    return NodeObservation(
        name=_metadata_name(raw),
        ready=any(c.type == "Ready" and c.status == "True" for c in _conditions(status)),
        unschedulable=spec.get("unschedulable") is True,
        control_plane=any(role in labels for role in CONTROL_PLANE_ROLES),
        allocatable_pods=pod_quantity(_mapping(status.get("allocatable")).get("pods")),
        infra=INFRA_ROLE in labels,
        tainted=any(_mapping(taint).get("effect") in BLOCKING_TAINTS for taint in taints),
    )


def pods_per_node_from(raw: JSON) -> dict[str, int]:
    """One page of a pod list as a ``meta.k8s.io/v1`` Table: how many rows name each node.

    The node is the cell of the column named ``Node``; ``<none>`` (not bound
    yet) counts for no node. Anything but a Table with that column is malformed.
    """
    table = _mapping(raw)
    if table.get("kind") != "Table":
        raise ValueError(f"expected a Table, got {table.get('kind')!r}")
    columns = table.get("columnDefinitions") or []
    if not isinstance(columns, list):
        raise TypeError("columnDefinitions is not a list")
    names = [_mapping(column).get("name") for column in columns]
    if "Node" not in names:
        raise ValueError("the pod Table has no Node column")
    index = names.index("Node")
    rows = table.get("rows") or []
    if not isinstance(rows, list):
        raise TypeError("rows is not a list")
    counts: dict[str, int] = {}
    for row in rows:
        cells = _mapping(row).get("cells")
        if not isinstance(cells, list) or len(cells) <= index:
            raise ValueError("a pod row has no Node cell")
        node = cells[index]
        if isinstance(node, str) and node and node != NO_NODE:
            counts[node] = counts.get(node, 0) + 1
    return counts
