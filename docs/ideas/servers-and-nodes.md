# Servers per hosted cluster, and moving nodes

**Status:** proposed.

## Servers per hosted cluster

server-scan is the source of truth for servers. On a hosted cluster's page,
list the servers under it from server-scan's servers-by-cluster read:
- name, MCE, InfraEnv;
- hardware (model, CPU, memory, disks);
- health.

A server's name links to its page in server-scan. This is read-only, through a
`ServerInventory` port with an adapter and a fake; it needs a server-scan
viewer token in a Secret.

The same read gives the free hosts per InfraEnv. That count is shown on the
create form as information. The check that refuses a create belongs to the
`create-cluster` workflow (workflow-runs.md), not to Wingman.

## Moving nodes between clusters

The idea: take a server out of cluster A's nodepool and give it to cluster
B. Two existing pieces are involved:
- the server-lifecycle workflows (`uninstall-server-from-hc`, `add-server-to-mce`);
- the InfraEnv pools herzi keeps filled.

A move means:
1. scale A's nodepool down by one, with that server named;
2. return the server to its InfraEnv pool;
3. scale B up.

Wingman shows both clusters' servers, lets an admin pick the server and the
target, and starts the steps. The steps themselves are workflows, not Wingman
code.

### Open questions

- **A named server.** Does a nodepool scale-down choose which Agent leaves?
  Today the NodePool releases any one. A move may need the workflow to
  cordon, drain and remove a named Agent.
- **The same InfraEnv.** Must both clusters use the same InfraEnv? If not, the
  server is re-installed into another pool, and that is
  `remove-server-from-mce` plus `add-server-to-mce`.
- **One workflow or many.** A `move-server` workflow would own the steps,
  their order and the rollback. Wingman then starts one run and shows it
  (workflow-runs.md).
