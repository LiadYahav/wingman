# Where Wingman sits in the platform architecture

The platform's architecture and its procedures are in `kubevirt-workflows`
(`docs/architecture.md`, `docs/procedures/`, `docs/inventory-controller.md`;
read at `f7b714e`). The team's architect wrote them and approves what Wingman
does. This file states how they divide the work between the systems, and
what that means for each idea in this folder. Facts about the systems
themselves are in `docs/ecosystem/README.md`.

> **Changed 2026-11-12** by the architect's vision ([single-pane.md](single-pane.md)):
> Wingman picks the MCE for a new cluster (question 1 below), ranks MCEs by
> what they hold and have free (rule 2 below, amended), and shows
> segments-manager's and server-scan's UIs. The rows and rules affected are
> marked; the rest stands.

## How the architect thinks

- **Git is the only truth; ArgoCD is the only thing that changes a cluster**
  (AD5, AD13). Workflows mutate Git and nothing else, on a branch, and a
  person merges.
- **Demand and supply are two loops**, and they touch only through what is
  observed on the hub. Customers write demand: create, scale, delete. The
  inventory controller keeps supply: each pool of ready nodes sits between a
  low and a high watermark. "Nothing in the demand column waits for the
  supply column": a cluster can be created with no workers available.
- **Pools, not pets.** An InfraEnv is one node type in one zone, shared by
  every cluster (AD21), and indifferent to who claims a node. A node released
  by one cluster goes back to the pool (after its disk is reset) for the
  next.
- **Absolute, never deltas.** Every count that crosses a boundary is the
  desired total, so a replay is harmless and the last request wins.
- **The workflow id is the dedup key**: one run in flight per target (for
  example per cluster and node type), so concurrent requests serialize
  instead of racing on one Git file.
- **Create, verify, never overwrite.** An existing resource is success when
  its identity matches; a hand correction survives a re-run.
- **Order is load-bearing in teardown.** Delete drains, removes the files,
  waits for ArgoCD to prune, waits for every node to be released and
  scrubbed, deletes the DHCP scope, and only then releases the segment.
- **Credentials never cross clusters.** A worker inside each cluster acts with
  its own account; only data comes back.
- **Hidden complexity.** The self-service catalog offers pre-packaged
  NodePool profiles; zones, placement and the Agent machinery stay out of
  sight (quality controls, ease of use). Tenants pick their own upgrade
  window.
- **Errors are RFC 9457 problem documents** on both HTTP services, as in
  Wingman (ADR-0004).

## Who owns what

| System | Owns | Wingman's part |
|---|---|---|
| Git (day1 values repo, NodePool files, `sigs/<team>`) | Desired state | Writes it by MR today: day1 until the create workflow exists (convention 13), and day2 |
| A person merging | Approval | Wingman's approvals page is where it happens, or GitLab (ecosystem question 5) |
| ArgoCD | Applying what is merged | Never applies anything; shows status once it can read it |
| Temporal workflows | Every operation with more than one step or system: create (03), scale (04), delete (05), upgrades (13-17), version band moves (18), adding and removing servers (01, 02). Validation, preflight and capacity admission live here | Starts the customer ones, passes totals, shows progress and errors in plain words, and links the run |
| Inventory controller (herzi), one per hub | Supply: pools between their watermarks | Never touches supply; shows a pool's state when a cluster waits for workers |
| server-scan | Every server's and VM's state, and the install lock | Read-only: the servers under a cluster, pool counts; **since 2026-11-12** its whole UI, rebuilt in Wingman on its unchanged API (whether its two writes come along is open, single-pane.md) |
| segments-manager, DHCP | Networks | Allocation and release happen inside workflows. ~~Never called by Wingman~~: Wingman reads a cluster's segment (ADR-0039) and, **since 2026-11-12**, shows segments-manager's read UI (single-pane.md) |
| **Wingman** | **The self-service catalog**: flavors (the NodePool profiles), forms that hide placement, MR review and approval, status, audit | |

## Rules Wingman follows from this

1. **Wingman doesn't orchestrate.** More than one step across systems is a
   workflow; Wingman starts it and shows it. The one exception, day1 create,
   edit and delete by MR, sits behind the `ClusterProvisioner` adapter until
   the workflows exist.
2. **Amended 2026-11-12:** Wingman ranks MCEs for a new cluster by what
   they hold and have free, and checks the free pods a control plane needs
   (single-pane.md, workstream 6); it still never reserves capacity. As first
   written: **Wingman never checks or reserves capacity.** The create and scale
   workflows will admit or refuse with a reason (their admission step is not
   built yet); Wingman shows the answer. While a cluster waits for workers,
   Wingman says why: the pool's spare count and the add-server runs filling
   it. The create procedure names this gap itself: "nothing here will tell
   the customer why".
3. **Every count Wingman sends is a total.**
4. **One writer per file.** Once a workflow owns a file (NodePools through
   update-nodepool), Wingman changes it through that workflow, never by its
   own commit.
5. **Wingman never names a server for a cluster.** Capacity moves through
   totals; the pools do the rest.
6. **Wingman never releases a network.** Teardown order belongs to the
   delete workflow.

## What this changes in the ideas

| Idea | Change |
|---|---|
| Release the segment on delete | **Dropped.** Releasing after the merge, before ArgoCD has pruned and the DHCP scope is gone, can hand a network to another cluster while its scope still exists. The delete workflow (05) owns this. |
| Moving nodes between clusters | **Reframed** as moving capacity: lower one cluster's total, raise another's, two absolute requests. No named server (servers-and-nodes.md). |
| Node-availability check before create | **Belongs to the create workflow's admission step**, which is not built yet. Create never waits for supply. Wingman shows a waiting cluster's pool state. |
| Flavors v2 | Flavors are the catalog's NodePool profiles. The sync of NodePool fields moves to update-nodepool when it exists (flavors-v2.md, "Where this is going"). |
| OCP upgrades | Two steps, control plane (14) then workers per node type (13), in a window the tenant picks. The surge capacity check is the workflow's (workflow-runs.md). |
| Bulk operations | If ever built: totals, one run per cluster and node type. |

## Questions for the architect

1. **Answered 2026-11-12: Wingman picks it** (single-pane.md, workstream 6).
   **Who picks the hub** for a new cluster: the catalog (Wingman, from
   version band and site) or the create workflow? Procedure 03 leaves it
   open; Wingman asks the user for site and MCE today, which the
   architecture wants hidden.
2. **Is Wingman's approvals page the merge** for workflow branches (03 step
   6), or does that stay in GitLab?
3. **Flavors and node types:** a workflow takes `worker_types` (node type and
   count). Is a flavor a set of node types with totals, and where do a
   nodepool's machine configs (network, chrony, NIC ring buffer) live in the
   VM model: in the node type, or per cluster?
4. **Does update-nodepool own every NodePool field** (replicas, configs,
   labels), so a flavor sync goes through it?
5. **Upgrades:** the sandbox `upgrade-cluster` workflow (one run, human gates)
   or procedures 13 and 14 (control plane and workers split)? Which one will
   Wingman drive?
