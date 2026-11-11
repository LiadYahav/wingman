# What an MCE hub shows about each node of an Agent-platform hosted cluster

Scope: what the MCE hub (HyperShift on MCE, with the Agent platform) records
about each worker of a hosted cluster, what it does not, and where upstream
sets each piece. It is the background of the nodes API
(`docs/notes/2026-11-11-cluster-nodes-api.md`, ADR-0038): Wingman reads only
the hub, read-only, through the same token as live status. It never reads a
hosted cluster's own API, and never a Secret.

Researched 2026-11-11 from the upstream open-source code. File paths are
relative to each repository at the refs below.

## Sources

| Repository | Refs read | Files that matter here |
|---|---|---|
| `openshift/hypershift` | `main@1caea768` (2026-11-10), `release-4.16` to `release-4.20` | `api/hypershift/v1beta1/nodepool_types.go`, `nodepool_conditions.go`; the NodePool controller `hypershift-operator/controllers/nodepool/` (`capi.go`, `conditions.go`, `nodepool_controller.go`); the in-place upgrader `control-plane-operator/hostedclusterconfigoperator/controllers/inplaceupgrader/inplaceupgrader.go` |
| `openshift/cluster-api-provider-agent` | `main`, `release-ocm-2.11`, `release-ocm-2.14` | `controllers/agentmachine_controller.go` (`findAgent`, `isValidAgent`, the delete hook), `api/v1beta1/agentmachine_types.go` |
| `openshift/assisted-service` | `main`, `release-ocm-2.11`, `release-ocm-2.14` | `api/v1beta1/agent_types.go`, `models/host.go` (states), `models/host_stage.go` (stages), `internal/controller/controllers/bmh_agent_controller.go` (BMAC) |
| `kubernetes-sigs/cluster-api` | `v1.8.4`, `v1.10.4`, `v1.14.3` | `api/v1beta1/condition_consts.go`, `api/v1beta1/machine_phase_types.go`, `internal/controllers/machine/machine_controller.go`, `machine_controller_phases.go` |
| `openshift/cluster-api` | `release-4.16` to `release-4.20` | The CAPI fork a hosted cluster's payload ships |

## Versions: who decides what

Four components write what the hub shows, and they move with different
versions:

| Component | Follows | Writes |
|---|---|---|
| HyperShift operator (NodePool controller, the CAPI CRDs) | the MCE | NodePool conditions, MachineSets and MachineDeployments, the NodePool annotation on Machines |
| In-place upgrader (in the hosted control plane's config operator) | the hosted cluster's release; identical from 4.16 to 4.20 | the in-place annotations on the MachineSet |
| CAPI Machine controller | the hosted cluster's payload | Machine phase, conditions, `nodeRef`, `nodeInfo` |
| Agent CAPI provider and assisted-service | the MCE | AgentMachines, Agents, the BareMetalHost label |

API versions:
- OpenShift 4.16 to 4.20 build on the CAPI v1beta1 Go types (vendored v1.7.1
  to v1.10.4). Up to 4.18 the CRDs serve and store only v1beta1.
- `status.v1beta2` exists only with a 4.19+ hosted cluster on 4.19+ operator
  CRDs. HyperShift `main` stores v1beta2.
- **Always request `cluster.x-k8s.io/v1beta1`:** every version serves it.
  The AgentMachine is `capi-provider.agent-install.openshift.io/v1beta1`
  (its storage version).
- A NodePool's `spec.management.upgradeType` is required and immutable:
  `Replace` or `InPlace`. `InPlace` is the team's chart's default
  (hostedclusters-setup), not HyperShift's.

## 1. Which NodePool a Machine belongs to

- **The annotation `hypershift.openshift.io/nodePool`** on a Machine is
  `<nodepool namespace>/<nodepool name>` (for example `hcp-foo/foo-infraenvA`).
  HyperShift itself finds a pool's Machines this way: it lists the Machines in
  the control-plane namespace and filters them by the annotation
  (`hypershift-operator/controllers/nodepool/capi.go`). The AgentMachine
  carries the same annotation, because CAPI copies the template's labels and
  annotations.
- **The control-plane namespace** is
  `<HostedCluster namespace>-<HostedCluster name, dots as dashes>`
  (`manifests.HostedControlPlaneNamespace`). For the team's clusters that is
  `hcp-<clusterName>-ocp4-<clusterName>`. Machines, MachineSets and
  AgentMachines live there; HostedClusters and NodePools live in
  `hcp-<clusterName>`.

The objects behind a NodePool `<np>`:

| | Replace | InPlace |
|---|---|---|
| MachineDeployment | `<np>` | none |
| MachineSet | `<np>-<5 random>`, label `cluster.x-k8s.io/deployment-name=<np>`, annotation `machinedeployment.clusters.x-k8s.io/revision` | `<np>` |
| Machine | `<machineset>-<5>`, labels `cluster.x-k8s.io/set-name=<machineset>` and `cluster.x-k8s.io/deployment-name=<np>` | `<np>-<5>`, label `cluster.x-k8s.io/set-name=<np>` |

## 2. InPlace updates: nothing on the hub names the node being updated now

How an in-place update runs:
1. The NodePool controller sets the target config on the pool's MachineSet.
2. The in-place upgrader picks up to `maxUnavailable` nodes, writes the
   desired config on those guest Nodes, and runs a machine-config-daemon pod
   per node.
3. When every node is done, it sets the current config to the target.

What it writes on the MachineSet `<np>`, in the control-plane namespace
(`inplaceupgrader.go`):

| Annotation (`hypershift.openshift.io/…`) | Value |
|---|---|
| `nodePoolTargetConfigVersion` | the target config hash |
| `nodePoolCurrentConfigVersion` | the current config hash; set to the target when done. An update is in progress while they differ |
| `nodePoolUpgradeInProgressTrue` | `"Nodepool update in progress. Target Config version: %s. Total Nodes: %d. Upgraded: %d"`; deleted when done |
| `nodePoolUpgradeInProgressFalse` | `"Node %s in nodepool degraded: %v"`, with the guest Node's name |
| `nodePoolMaxUnavailable` | how many nodes update at once |

**The state of each node lives only on the guest Nodes**: the
`machineconfiguration.openshift.io/` annotations (`desiredConfig`,
`currentConfig`, `state`, `reason`, `desiredDrain`, `lastAppliedDrain`), and
the pod `machine-config-daemon-<node>` in the namespace `<np>-upgrade`.
Reading them needs the hosted cluster's admin kubeconfig, a Secret on the hub.
That is out of scope for Wingman. On `main` only, the upgrader also sets the
Machine annotation `hypershift.openshift.io/release-version` once its node is
done.

What the hub shows instead (CAPI copies it from the guest Node):
- Machine `status.nodeInfo` (`kubeletVersion`, `osImage`, `bootID`,
  `systemUUID`). `bootID` changes on every reboot.
- The Machine condition `NodeHealthy` goes False or Unknown with the reason
  `NodeConditionsFailed` and a message such as
  `"Node condition Ready is Unknown. "` while the node reboots. **Cordon and
  drain are not reflected.**
- The NodePool condition `AllNodesHealthy` lists
  `"Machine <name>: <NodeHealthy reason>\n"` per unhealthy Machine (4.16 to
  4.20). `AllMachinesReady` stays True during a reboot.

The NodePool conditions of an in-place update are `UpdatingVersion` and
`UpdatingConfig`; a failure has the reason `InplaceUpgradeFailed`. Their text
depends on the operator's version:

| Operator | While updating | When a node is degraded | Source |
|---|---|---|---|
| 4.16 to 4.18 | True (AsExpected), `"Updating Version, Target: <hash>"` or `"Updating Config, Target: <hash>"`, when the MachineSet has `nodePoolUpgradeInProgressTrue`; else the literal status `"unknown"` | False, `InplaceUpgradeFailed`, same text | `hypershift-operator/controllers/nodepool/capi.go` |
| 4.19, 4.20, `main` | the MachineSet annotation's own text: `"Nodepool update in progress. Target Config version: <hash>. Total Nodes: <n>. Upgraded: <k>"` | False, `InplaceUpgradeFailed`, `"Node <node> in nodepool degraded: <reason>"` | `hypershift-operator/controllers/nodepool/conditions.go` |

Before the upgrader picks the update up, both can briefly show the generic
`"Updating version in progress. Target version: %s"` or
`"Updating config in progress. Target config: %s"`. `UpdatingVersion` is True
while `status.version` differs from the target; `status.version` is set only
when the update is done.

So during an in-place update the hub tells how far it is (k of n), which node
is rebooting (its `NodeHealthy` is not True), and which node is degraded. It
does not show the drain before a reboot, nor which node goes next.

## 3. Replace updates

A Replace update is a CAPI rollout: new Machines from a new MachineSet,
old ones drained and deleted.

Machine `status.phase` (`api/v1beta1/machine_phase_types.go`):

| Phase | Means |
|---|---|
| `Pending`, `Provisioning` | created; no Agent yet |
| `Provisioned` | an Agent is reserved (`spec.providerID` set) |
| `Running` | the Node exists (`status.nodeRef` set) |
| `Deleting`, `Deleted` | a deletion timestamp is set |
| `Failed` | `status.failureReason` and `failureMessage` say why |
| `Unknown` | |

**New or old:** a Machine is new when the MachineSet named by its
`cluster.x-k8s.io/set-name` label has the highest revision annotation of the
pool's MachineSets; any other is old and will be replaced.

A deleting Machine walks through these v1beta1 conditions, in order
(`internal/controllers/machine/machine_controller.go`):

| Condition | False with reason | Means |
|---|---|---|
| `PreDrainDeleteHookSucceeded` | `WaitingExternalHook` | a pre-drain hook holds it |
| `DrainingSucceeded` | `Draining` ("Draining the node before deletion"), or `DrainingFailed` | the node is being drained |
| `VolumeDetachSucceeded` | `WaitingForVolumeDetach` | volumes are detaching |
| `PreTerminateDeleteHookSucceeded` | `WaitingExternalHook` | **always, on the Agent platform**: see below |
| `NodeHealthy` | `Deleting`, `DeletionFailed` | |

The Agent provider holds the pre-terminate hook
`pre-terminate.delete.hook.machine.cluster.x-k8s.io/agentmachine`
(`controllers/agentmachine_controller.go`) until the Agent's
`debugInfo.state` is one of `discovering-unbound`, `known-unbound`,
`disconnected-unbound`, `insufficient-unbound`, `disabled-unbound`,
`unbinding-pending-user-action` or `error`: that is, until the host has
rebooted into discovery.

Other Machine signals:
- `NodeHealthy` reasons: `WaitingForNodeRef`, `NodeProvisioning`,
  `NodeNotFound`, `NodeConditionsFailed`, `NodeInspectionFailed`.
- `InfrastructureReady` mirrors the AgentMachine's `Ready` (falling back to
  `WaitingForInfrastructure`).
- The MachineDeployment's status has `replicas`, `updatedReplicas`,
  `readyReplicas`, `availableReplicas`, `unavailableReplicas` and `phase`.
- With v1beta2 (4.19+ only), `status.v1beta2.conditions` adds `Deleting`
  (reasons `NotDeleting`, `WaitingForPreDrainHook`, `DrainingNode` "Drain not
  completed yet (started at …)", `WaitingForVolumeDetach`,
  `WaitingForPreTerminateHook`, `WaitingForInfrastructureDeletion`,
  `WaitingForBootstrapDeletion`, `DeletingNode`, `DeletionCompleted`),
  `UpToDate` (old or new) and `NodeReady`, and `status.deletion` has
  `nodeDrainStartTime` and friends. Prefer them when present.

## 4. Fewer ready nodes than wanted

Every Machine has an AgentMachine of the same name
(`Machine.spec.infrastructureRef.name`) in the control-plane namespace. The
AgentMachine reserves an Agent for it.

AgentMachine conditions (`api/v1beta1/agentmachine_types.go`):
- `AgentReserved` is True once `status.agentRef` is set. Otherwise it is
  False with `NoSuitableAgents` (a warning with an **empty** message) or
  `AgentNotYetFound` (the message is the error's text).
- `AgentSpecSynced`, `AgentValidated`, `AgentRequirementsMet` and `Installed`
  are False `AgentNotYetFound` "Agent not yet reserved" before a reservation.
  After it, each mirrors the Agent's own condition.
- `Ready` is their summary, "<k> of 5 completed".

**No free Agent** looks like this, at three levels:
- AgentMachine: `AgentReserved` False `NoSuitableAgents`, empty message.
- Machine: `InfrastructureReady` reason `NoSuitableAgents`, "0 of 5 completed".
- NodePool: `AllMachinesReady` "<n> of <m> machines are not ready\nMachine
  <m>: NoSuitableAgents\n". With no Machines at all: "No Machines are created"
  (`NotFound`).

**A free Agent**, by the provider's rule (`findAgent`, `isValidAgent`):
searched in the HostedCluster's `spec.platform.agent.agentNamespace`, an
Agent is free when
- its labels match the NodePool's `spec.platform.agent.agentLabelSelector`,
- it has no `agentMachineRef` label,
- `spec.approved` is true,
- and its conditions are `Validated` True, `Connected` True and `Bound` False.

When it is bound, the Agent gets the label `agentMachineRef=<AgentMachine>`,
the annotation `agentMachineRefNamespace`, and `spec.clusterDeploymentName`.
While it installs, its `Installed` condition is False
`InstallationInProgress` "The installation is in progress: <statusInfo>".

Names along the way:
- `AgentMachine.spec.providerID` is `agent://<agent name>`, copied to
  `Machine.spec.providerID`.
- The guest Node's name is the Agent's hostname;
  `Machine.status.nodeRef.name` gives it.

## 5. From an Agent to its server

What an Agent says about itself (`api/v1beta1/agent_types.go`):
- `status.debugInfo.state` and `stateInfo` (also the annotations
  `agent.agent-install.openshift.io/state` and `/current-stage`). The states
  (`models/host.go`): discovering, known, disconnected, insufficient,
  disabled, preparing-for-installation, preparing-failed,
  preparing-successful, pending-for-input, installing,
  installing-in-progress, installing-pending-user-action,
  resetting-pending-user-action, installed, error, resetting,
  added-to-existing-cluster, cancelled, binding, unbinding,
  unbinding-pending-user-action, known-unbound, disconnected-unbound,
  insufficient-unbound, disabled-unbound, discovering-unbound, reclaiming,
  reclaiming-rebooting.
- `status.progress.currentStage` (`models/host_stage.go`): Starting
  installation, Waiting for control plane, Waiting for bootkube, Waiting for
  controller, Installing, Writing image to disk, Rebooting, Waiting for
  ignition, Configuring, Joined, Done, Failed (`main` adds "Copying registry
  data to disk"). A worker ends Joined, then Done.
- The host: `spec.hostname`, `status.inventory.hostname`,
  `status.inventory.systemVendor.{serialNumber,manufacturer,productName}`,
  `status.inventory.interfaces[].macAddress`, `status.inventory.bmcAddress`.
- Labels: `agent-install.openshift.io/bmh` (below), `agentMachineRef`, and
  `infraenvs.agent-install.openshift.io=<InfraEnv>`.

**The BareMetalHost label.** The BareMetalHost agent controller (BMAC,
`internal/controller/controllers/bmh_agent_controller.go`) matches each
BareMetalHost's `spec.bootMACAddress` with the Agents' interface MACs, and
labels the Agent `agent-install.openshift.io/bmh=<BareMetalHost name>`.

**The chain from a Machine to its server:**

```
Machine.spec.infrastructureRef.name
  → AgentMachine (same namespace)
  → status.agentRef {namespace, name}   (or spec.providerID minus "agent://")
  → Agent
  → label agent-install.openshift.io/bmh
  → BareMetalHost name = server-scan's server name
```

When the label is missing (an Agent not booted through a BareMetalHost, or
before BMAC labels it), two fallbacks:
1. **MAC:** the Agent's interface MACs against the server's MACs in
   server-scan (the install workflow takes the BareMetalHost's
   `bootMACAddress` from them: `server-scan.md` §4).
2. **Serial:** the Agent's `systemVendor.serialNumber` against the server's
   serial.

**A BareMetalHost name is a Kubernetes name**: a lowercase DNS subdomain
(RFC 1123). server-scan's names can hold upper case (a serial such as
`ocp-dell-r660-site1-64c-512gb-DL0000123`), so the BareMetalHost made for
that server is the lowercase `…-dl0000123`. Wingman therefore matches a
BareMetalHost name to a server name ignoring case.

## 6. What the token must read

Read-only, `get` and `list`:

| API group | Resources | Namespace |
|---|---|---|
| `hypershift.openshift.io` | `hostedclusters`, `nodepools` | `hcp-<clusterName>` |
| `cluster.x-k8s.io` | `machines`, `machinesets` | `hcp-<clusterName>-ocp4-<clusterName>` |
| `capi-provider.agent-install.openshift.io` | `agentmachines` | the control-plane namespace |
| `agent-install.openshift.io` | `agents`, `infraenvs` | the HostedCluster's `agentNamespace` |

Control-plane namespaces are created per cluster, so a ClusterRole with a
ClusterRoleBinding is the simple grant. MachineDeployments are not needed:
the MachineSets' revision annotation tells old from new. No Secrets. The
ready-to-apply YAML is in `deploy/helm/wingman/README.md` (Live cluster
status), and the upgrade steps in `docs/upgrade/3.3-to-3.4.md`.

## What Wingman uses

How the nodes API (`docs/notes/2026-11-11-cluster-nodes-api.md` §1) reads
each piece above. A NodePool:

| Field | From | § |
|---|---|---|
| `wanted`, `autoscaling` | `spec.replicas`, `spec.autoScaling.{min,max}` | |
| `ready`, `version` | `status.replicas`, `status.version` (set only when an update is done) | 2 |
| `upgrade_type`, `agent_selector` | `spec.management.upgradeType`, `spec.platform.agent.agentLabelSelector` | Versions, 4 |
| `update` | not null while `UpdatingVersion`, `UpdatingConfig` or `UpdatingPlatformMachineTemplate` is not False; `message` is its text, passed through | 2 |
| `update.progress` | `Total Nodes: n. Upgraded: k`, from the condition (4.19+ operators) or the MachineSet's `nodePoolUpgradeInProgressTrue` (older ones); `null` otherwise, and always for Replace | 2 |
| `update.failed` | the reason `InplaceUpgradeFailed` | 2 |
| `problems` | `Ready`, `AllMachinesReady`, `AllNodesHealthy` when not True | 2, 4 |
| `free_agents` | the Agents in `agentNamespace` that match the selector, and those free by the provider's rule | 4 |

A node (one Machine, grouped by its `hypershift.openshift.io/nodePool`
annotation):

| Field | From | § |
|---|---|---|
| `state` `deleting` | a deletion timestamp | 3 |
| `state` `failed` | phase `Failed`, or the node `nodePoolUpgradeInProgressFalse` (or an `InplaceUpgradeFailed` message) names | 2, 3 |
| `state` `waiting` | the AgentMachine's `AgentReserved` not True | 4 |
| `state` `installing` | reserved, the Agent not installed yet | 4 |
| `state` `joining` | installed, `status.nodeRef` empty | 3 |
| `state` `not_ready` | `NodeHealthy` not True | 2, 3 |
| `state` `missing` | the pool wants more than its non-deleting Machines | |
| `activity` | deleting: the first unmet deletion condition (or v1beta2 `Deleting`), as "Draining", "Waiting for volumes to detach" or "Waiting for the host to return to discovery" (the pre-terminate hook). Installing: the Agent's `currentStage`. Joining: "Joining the cluster". Not ready: "Rebooting for the update (…)" with the `NodeHealthy` message while the pool updates in place, "Node not ready: …" otherwise. Failed in place: the degraded reason | 2, 3, 5 |
| `current` | InPlace: the `not_ready` nodes while the pool updates, and the degraded one (the drain and the next node are not visible). Replace: every Machine `deleting`, `installing`, `joining` or `waiting` while the pool updates | 2, 3 |
| `outdated` | Replace only: the Machine's MachineSet is not the highest revision | 3 |
| `waiting_for` | the `AgentReserved` reason (`NoSuitableAgents`, `AgentNotYetFound`) and `free_agents`, in words | 4 |
| `agent` | the Agent's `debugInfo.state` and `progress.currentStage` | 5 |
| `server_name` | the Agent's `agent-install.openshift.io/bmh` label, else the MAC or serial match; compared with server-scan's names ignoring case | 5 |

What Wingman does not show, because only the guest cluster has it: the
cordon and drain of an in-place update, which node it takes next, and each
node's machine-config state.
