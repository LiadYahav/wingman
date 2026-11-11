# ADR-0038: Cluster nodes come from the MCE by NodePool, joined to server-scan; uninstall starts the platform's workflow

Date: 2026-11-11
Status: Accepted

## Context

The cluster page needed each NodePool's nodes:
- what is there, and what a short pool is missing and why;
- during an update, which node is being worked on;
- each node's server: its health, and a link to it.

The first design (the same day) listed the servers server-scan places in a
cluster. That answers "which servers", but not "which NodePool", "why is a
node missing" or "what is the update doing". Only the MCE hub knows those.

The MCE holds the objects behind each NodePool. They are described, with
upstream sources, in `docs/ecosystem/notes/hypershift-node-state.md`:
- the CAPI Machines and their MachineSets, in the cluster's control-plane
  namespace;
- the AgentMachine each Machine's `spec.infrastructureRef` names;
- the Agent the AgentMachine reserved, whose `agent-install.openshift.io/bmh`
  label names its BareMetalHost, which is server-scan's server.

server-scan is the platform's record of physical servers
(`docs/ecosystem/notes/server-scan.md`). Its `nodes-status` jobs write each
server's `cluster_name`, as the HostedCluster's name or the bare
`clusterName`.

Taking a node out is the platform's `uninstall-server-from-hc` workflow
(`docs/ecosystem/notes/workflows.md` §1a.6). Every refusal after the start
is a FAILED run whose error names the reason, for example
`ClusterMembershipMismatchError` or `ServerNotInServerScanError`.

The user decided (2026-11-11) that **Wingman starts the workflow and shows
its run; the procedure and its checks are the workflow's.** The orchestrator
has no auth and no field for who asked.

## Decision

- **Nodes come from the cluster's MCE, by NodePool**, through the hub access
  live status already has (`CLUSTER_STATUS_ENABLED`, a token per MCE). The
  route answers 501 without it.
  - `HubApi` gains four read-only lists: `machines` and `machine_sets`, always
    as `cluster.x-k8s.io/v1beta1` (4.16 to 4.18 serve nothing newer);
    `agent_machines`; and `agents` in the HostedCluster's
    `spec.platform.agent.agentNamespace`.
  - The token's service account needs `get` and `list` on them (the contract's
    §4; the chart README has the ClusterRole). Without the grant the route
    answers 502, naming the denied path.
  - The view caches the reads for at most 10 s per replica (ADR-0011). Live
    status keeps reading the hub directly.
- **The join is pure** (`wingman_day1.domain.node_pools`), and each rule of
  `docs/notes/2026-11-11-cluster-nodes-api.md` §1 is one function:
  - A Machine belongs to the NodePool its `hypershift.openshift.io/nodePool`
    annotation names (`<namespace>/<pool>`).
  - A Machine leads to its AgentMachine, then to the Agent (`status.agentRef`,
    or `spec.providerID`), then to the server. The server is matched by the
    BareMetalHost name, ignoring case (a Kubernetes name is lowercase), then
    by MAC, then by serial.
  - The node's state comes from the first rule that holds: deleting, failed,
    waiting, installing, joining, not ready, ready. `activity` and `current`
    say what the update is doing to it.
  - A waiting Machine says why, from the AgentMachine's reason and the pool's
    Agents. The free-Agent rule is the provider's own (`isValidAgent`), and
    the label selector is applied with Kubernetes' rules.
  - A pool short of Machines gets one `missing` row per Machine it lacks.
  - An in-place update's progress and its degraded node come from the
    condition text (4.19+ operators) or the MachineSet's annotations (4.16 to
    4.18). Both use the same `Total Nodes: n. Upgraded: k` and
    `Node <n> in nodepool degraded: <reason>` texts.
  - Phases, reasons and messages are upstream's strings, passed through.
- **server-scan is optional.**
  - It adds each node's server record, and the `unassigned` servers: those it
    places in the cluster that no Machine leads to.
  - It is read once for the whole fleet (`GET /api/v1/servers/rows`), cached,
    and revalidated with its `ETag`. If it cannot be read, the nodes are
    listed without servers and `server_scan_error` says why.
- **Runs** come from one cached list of the fleet's 200 newest uninstall runs.
  - A server's run is found by its deterministic id, or through server-scan's
    lock. The matched runs are read for their step and error.
  - If the orchestrator cannot be read, the nodes are listed and `runs_error`
    says why.
- **Uninstall** is for admins only.
  - The node's name is typed again, compared ignoring case.
  - Day1 reads the server fresh and checks one thing: a Machine of the cluster
    leads to it, or server-scan places it in the cluster. If not, it refuses
    with 409 `NODE_NOT_IN_CLUSTER`. That check makes the button act on what
    the page showed. Everything else (the MCE, a contested claim, maintenance,
    another run's lock) is the workflow's to check.
  - The start sends `server_names` (one name) and `mce_cluster` (the cluster's
    MCE folder), plus `namespace` when `MCE_INFRAENV_NAMESPACE` is set. Day1
    logs who started it, as the structured event `node_uninstall_started`.
- **A start is a write and is never retried** (ADR-0006).
  - Refused before it was sent, refused by the orchestrator, or any 5xx but a
    gateway's 504: 502 `DEPENDENCY_UNAVAILABLE`, nothing started.
  - Sent without an answer (a read timeout, a dropped connection, a gateway's
    504, an unreadable 202): 504 `AMBIGUOUS_WRITE`; look at the node's run
    first.
  - The orchestrator's 409: 409 `UNINSTALL_ALREADY_RUNNING`.
  - After any start, the cached runs are dropped.
- **Off by default.**
  - The nodes route needs live status.
  - Uninstall needs both `SERVER_SCAN_URL` and `WORKFLOWS_API_URL`.
  - `WORKFLOWS_API_URL` without `SERVER_SCAN_URL` refuses to start
    (ADR-0009), and the chart refuses to render it.
- **`DAY1_FAKE_FLEET=true`** (development only) replaces the MCE hubs,
  server-scan and the orchestrator with fakes from `dev/fleet-fixtures/`.
  The fake MCE is built as Kubernetes JSON and read with the adapter's own
  parsers.

## Why the MCE only, and the in-place limit

Wingman never reads a hosted cluster's own API. That would need each
cluster's admin kubeconfig Secret on the MCE: a credential for every
customer cluster, and so a far larger grant than read-only lists of
Machines and Agents.

So the per-node detail of an InPlace update is not visible. The upgrader
cordons and drains a node, runs the machine-config daemon on it, and
reboots it; that state lives only on the hosted cluster's Nodes. The hub
shows a node only once its reboot makes the Machine's `NodeHealthy` False.
The drain before the reboot, and which node the update takes next, are not
shown, and the contract says so. A Replace rollout is fully visible on the
hub: the deleting Machine's drain step, and the new Machine's install stage.

## Alternatives rejected

- **The nodes from server-scan alone** (the first design): it cannot tell
  NodePools, missing nodes or update progress.
- **Reading the hosted cluster's Nodes** for the in-place detail: it needs
  every cluster's admin kubeconfig (above).
- **Checking the MCE, a contested claim, maintenance or a held lock before
  starting**: the workflow checks these against the MCE itself and reports a
  refusal as a failed run with its reason. A second copy in Wingman would
  drift from the procedure.
- **`GET /api/v1/servers?cluster_name=` per cluster**: it takes one name per
  call.
- **Calling the orchestrator from the browser**: it has no auth and no CORS.

## Consequences

- An operator grants each MCE token the new reads before the nodes view
  works (`docs/upgrade/3.3-to-3.4.md`). Live status works without the grant.
- An empty `unassigned` with server-scan read means every server it places
  in the cluster is a node.
- A failed in-place update names its degraded node; the node being drained
  before a reboot shows as ready until it reboots.
- The run list holds the fleet's 200 newest runs. An older running run is
  found through server-scan's lock; an older finished one is not shown.
- Upstream renames a condition reason or a phase without a Wingman change:
  they are passed through. A renamed annotation or condition type would need
  one, and the source-backed note says where each comes from.
- The web matches two new codes, both 409: `NODE_NOT_IN_CLUSTER` and
  `UNINSTALL_ALREADY_RUNNING`.

## Verification

- `apps/day1-service/tests/unit/domain/test_node_pools.py` and
  `test_selectors.py`: every join rule, the free-Agent rule, both in-place
  formats, the selector's operators and the server match's fallbacks.
- `tests/unit/infrastructure/test_hub_api_machines.py`: the new reads against
  upstream's shapes. A 404 is "not served", a 403 names the path, and
  malformed objects are unavailable.
- `tests/unit/infrastructure/test_fake_mce.py`: the fake MCE fits every
  fixture cluster and server, and each scenario reads as described.
- `tests/unit/application/test_nodes.py` and `tests/api/test_nodes_api.py`:
  - the contract's shapes and codes;
  - server-scan or the orchestrator absent or failing;
  - every uninstall refusal, and the ambiguous start.
- `tests/unit/infrastructure/test_server_scan.py` and `test_workflows_api.py`,
  against `httpx.MockTransport` with the live shapes (read by GET only,
  2026-11-11), and the saved OpenAPI document.
- `tests/repo/test_chart_env_contract.py`: the chart's variables, values kept
  from a 3.3 release included.
