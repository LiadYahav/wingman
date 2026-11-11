# Servers per hosted cluster, waiting for workers, and moving capacity

**Status:** a hosted cluster's nodes by NodePool, and why a pool waits for
workers, **built** 2026-11-11 (ADR-0038), with uninstalling one node through
the platform's workflow; the rest proposed.
Checked against [architecture-fit.md](architecture-fit.md): server-scan is
the platform's state tracker for servers and VMs (AD15), and nodes come from
shared pools, not from named servers (AD21).

## Servers per hosted cluster

**Built** (ADR-0038; the API is `docs/notes/2026-11-11-cluster-nodes-api.md`,
the sources `docs/ecosystem/notes/hypershift-node-state.md`). A hosted
cluster's page shows each NodePool's nodes from its MCE, each Machine followed
to its Agent and its server in server-scan:
- each node's state, what is happening to it now, and whether the pool's
  update is working on it;
- for a short pool, the missing Machines and why a Machine waits (no free
  Agent, and why each matching one is not free);
- each server's serial, vendor and model, health, maintenance, the stale and
  contested flags, and a link to its page in server-scan;
- the servers server-scan places in the cluster that no Machine leads to.

An admin can start the platform's `uninstall-server-from-hc` workflow on one
node and follow its run. The workflow owns the procedure and its checks;
Wingman starts it and shows the run.

Left for later: the InfraEnv and the hardware detail (CPU, memory, disks).
server-scan's fleet rows do not carry them; they need one detail read per
server.

## Why a cluster waits for workers

Creating or scaling a cluster writes demand and stops. Workers arrive when
the inventory controller sees the demand and fills the pool. With an empty
pool, the cluster sits with zero workers, and the create procedure says
"nothing here will tell the customer why". Wingman can:

- show each NodePool's wanted and ready counts;
- show, for each pool it draws on (node type and zone), the spare count and
  the add-server runs filling it;
- say it in words: "waiting for 2 workers in pool `32-128-zone-1`; 2
  servers are being added".

All of it is read-only and observed (server-scan, the orchestrator's runs,
the hub's NodePools). Wingman never checks or reserves capacity: the create
and scale workflows' admission step will refuse with a reason or give an
estimate (not built yet), and Wingman shows that answer.

## Moving capacity between clusters

The original idea was to take a server out of cluster A and give it to
cluster B. The platform doesn't work with named servers: a pool is shared,
and indifferent to who claims a node. Moving capacity is therefore:

1. lower A's total for that node type;
2. raise B's total.

That is two absolute requests through the scale workflow (update-nodepool,
procedure 04), one per cluster. The released node goes back to the pool,
after its disk is reset because it held A's data, and B's NodePool claims
whatever is spare. If the pool is short, the inventory controller adds a
server.

Wingman's part is one form ("move 2 nodes of type X from A to B") that
starts both runs and shows them. A bad hypervisor or a broken server is the
platform team's concern, not a tenant move.

### Open questions

- **The order of the two requests.** Raise B first, which needs spare
  capacity, or lower A first, which takes A's capacity before B has its own?
  The architecture's surge rule (new before old) suggests raising B first.
- **Bare metal today.** The current fleet is bare-metal Agents in per-hardware
  InfraEnvs, not VM pools. A move between two clusters on different InfraEnvs
  is not a move: it is a server leaving one pool and joining another
  (remove-server, then add-server), which the inventory controller does on
  its own when demand shifts.
