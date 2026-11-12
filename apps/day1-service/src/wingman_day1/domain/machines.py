"""What an MCE hub holds about a hosted cluster's workers (ADR-0038).

Read-only observations of the objects behind each NodePool, in the cluster's
control-plane namespace and its agent namespace:

- a CAPI ``Machine`` per node (``cluster.x-k8s.io/v1beta1``), and the
  ``MachineSet`` it belongs to;
- the ``AgentMachine`` the Machine's ``spec.infrastructureRef`` names
  (``capi-provider.agent-install.openshift.io/v1beta1``);
- the ``Agent`` reserved for it (``agent-install.openshift.io/v1beta1``), the
  discovered host, which names its BareMetalHost.

``docs/ecosystem/notes/hypershift-node-state.md`` says what each field means
and where upstream sets it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from wingman_day1.domain.status import Condition

NODE_POOL_ANNOTATION: Final = "hypershift.openshift.io/nodePool"
"""On Machines and MachineSets: ``<nodepool namespace>/<nodepool name>``."""
SET_NAME_LABEL: Final = "cluster.x-k8s.io/set-name"
DEPLOYMENT_NAME_LABEL: Final = "cluster.x-k8s.io/deployment-name"
REVISION_ANNOTATION: Final = "machinedeployment.clusters.x-k8s.io/revision"
UPGRADE_IN_PROGRESS_ANNOTATION: Final = "hypershift.openshift.io/nodePoolUpgradeInProgressTrue"
"""An in-place update's progress text, on the pool's MachineSet."""
UPGRADE_DEGRADED_ANNOTATION: Final = "hypershift.openshift.io/nodePoolUpgradeInProgressFalse"
"""An in-place update's degraded node, on the pool's MachineSet."""
BMH_LABEL: Final = "agent-install.openshift.io/bmh"
"""On an Agent: its BareMetalHost's name, which is the server's name in server-scan."""
AGENT_MACHINE_REF_LABEL: Final = "agentMachineRef"
INFRA_ENV_LABEL: Final = "infraenvs.agent-install.openshift.io"
"""The InfraEnv (the node type) an Agent was discovered in."""
"""On an Agent: the AgentMachine that took it. A labelled Agent is not free."""
PROVIDER_ID_PREFIX: Final = "agent://"


def condition(conditions: tuple[Condition, ...], kind: str) -> Condition | None:
    """The condition of type ``kind``, if reported."""
    return next((c for c in conditions if c.type == kind), None)


def is_true(conditions: tuple[Condition, ...], kind: str) -> bool:
    """Whether the condition ``kind`` is reported True."""
    found = condition(conditions, kind)
    return found is not None and found.status == "True"


@dataclass(frozen=True, slots=True)
class MachineObservation:
    """A CAPI Machine: one worker, wanted or there."""

    name: str
    node_pool: str | None = None
    """The ``hypershift.openshift.io/nodePool`` annotation, ``<namespace>/<name>``."""
    machine_set: str | None = None
    """The ``cluster.x-k8s.io/set-name`` label."""
    infrastructure_ref: str | None = None
    """``spec.infrastructureRef.name``: its AgentMachine."""
    provider_id: str | None = None
    """``spec.providerID``: ``agent://<agent name>`` once an Agent is reserved."""
    phase: str | None = None
    node_name: str | None = None
    """``status.nodeRef.name``: the hosted cluster's Node, once it joined."""
    deleting: bool = False
    """It has a deletion timestamp."""
    failure_reason: str | None = None
    failure_message: str | None = None
    conditions: tuple[Condition, ...] = ()
    v1beta2_conditions: tuple[Condition, ...] = ()
    """``status.v1beta2.conditions``: only with a 4.19+ hosted cluster and CRDs."""

    @property
    def agent_name(self) -> str | None:
        """The Agent named by ``spec.providerID``, if any."""
        if self.provider_id and self.provider_id.startswith(PROVIDER_ID_PREFIX):
            return self.provider_id.removeprefix(PROVIDER_ID_PREFIX) or None
        return None


@dataclass(frozen=True, slots=True)
class MachineSetObservation:
    """A CAPI MachineSet: an InPlace pool's only one, or one revision of a Replace pool."""

    name: str
    node_pool: str | None = None
    deployment: str | None = None
    """The ``cluster.x-k8s.io/deployment-name`` label (Replace pools)."""
    revision: int | None = None
    """``machinedeployment.clusters.x-k8s.io/revision``: the highest is the newest."""
    upgrade_in_progress: str | None = None
    upgrade_degraded: str | None = None


@dataclass(frozen=True, slots=True)
class AgentMachineObservation:
    """The Agent provider's AgentMachine: which Agent it reserved, and how that went."""

    name: str
    agent_name: str | None = None
    """``status.agentRef.name``, set once an Agent is reserved."""
    conditions: tuple[Condition, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentObservation:
    """An Agent: a discovered host in the cluster's agent namespace."""

    name: str
    labels: Mapping[str, str] = field(default_factory=dict)
    approved: bool = False
    hostname: str | None = None
    state: str | None = None
    """``status.debugInfo.state``, e.g. ``installing-in-progress``."""
    stage: str | None = None
    """``status.progress.currentStage``, e.g. ``Writing image to disk``."""
    serial: str | None = None
    """``status.inventory.systemVendor.serialNumber``."""
    macs: tuple[str, ...] = ()
    """``status.inventory.interfaces[].macAddress``."""
    conditions: tuple[Condition, ...] = ()

    @property
    def bmh(self) -> str | None:
        """Its BareMetalHost's name, from the ``agent-install.openshift.io/bmh`` label."""
        return self.labels.get(BMH_LABEL) or None

    @property
    def infra_env(self) -> str | None:
        """Its InfraEnv, the node type, from the ``infraenvs.agent-install.openshift.io`` label."""
        return self.labels.get(INFRA_ENV_LABEL) or None

    @property
    def taken_by(self) -> str | None:
        """The AgentMachine that took it, from the ``agentMachineRef`` label."""
        return self.labels.get(AGENT_MACHINE_REF_LABEL) or None
