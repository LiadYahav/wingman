# Fleet versions and pool capacity

**Status:** proposed. Read-only views for the platform team, built on the
architecture's constraints (C3, C4: an MCE supports a window of OCP versions)
and its supply loop (the inventory controller's pools and watermarks).

## Versions and bands

One page for the fleet's versions:

- Every hosted cluster's OCP version, grouped by its MCE, beside the window
  that MCE supports.
- **Clusters at the edge.** A cluster on the newest version its MCE allows
  can't upgrade further there. Its next step is a version band move
  (procedure 18, a rebuild on another MCE), and that takes planning.
- **Blocked by order.** The fleet upgrades top down (seed, KubeVirt cluster,
  MCE, control plane, workers): show what each layer waits on.
- When an MCE is due to retire, list the clusters that must move first.

Read from day1 (`mastertag`, the MCE's `version.yaml`) and the orchestrator's
upgrade targets. It decides nothing: it shows where upgrades are blocked
before someone hits the block.

## Pools

For each MCE and each pool (node type and zone), the inventory controller's
numbers:
- demand: the NodePools' wanted replicas;
- assigned and spare agents;
- servers being added;
- the low and high watermarks.

A pool short of demand, or stuck near its floor, is visible before a tenant
asks why their cluster has no workers (servers-and-nodes.md). Pools near the
high watermark show when a new cell will be needed (SC5).

Read from the hub's NodePools and Agents, server-scan and the orchestrator's
runs, through ports; Wingman changes nothing here.

## Open questions

- Which hub reads need credentials Wingman doesn't have today? Live status
  reads the MCEs already (`clusterStatus`).
- Are the watermarks readable (the controller's ConfigMap on each hub)?
