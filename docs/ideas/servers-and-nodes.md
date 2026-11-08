# Servers per hosted cluster, waiting for workers, and moving capacity

**Status:** proposed. Checked against [architecture-fit.md](architecture-fit.md):
server-scan is the platform's state tracker for servers and VMs (AD15), and
nodes come from shared pools, not from named servers (AD21).

## Servers per hosted cluster

On a hosted cluster's page, list the servers under it, read from server-scan's
servers-by-cluster read:
- name, MCE, InfraEnv;
- hardware (model, CPU, memory, disks);
- health.

A server's name links to its page in server-scan. This is read-only, through a
`ServerInventory` port with an adapter and a fake; it needs a server-scan
viewer token in a Secret.

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
