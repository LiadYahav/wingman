# ADR-0038: Cluster nodes come from server-scan; uninstall starts the platform's workflow

Date: 2026-11-11
Status: Accepted

## Context

Wingman knew nothing about the servers under a hosted cluster. server-scan
is the platform's record of physical servers
(`docs/ecosystem/notes/server-scan.md`). Its `nodes-status` jobs set each
server's `cluster_name`, and between them they write the HostedCluster's
name (`ocp4-<clusterName>`) or the bare `clusterName`.

Taking a node out of a hosted cluster is the platform's
`uninstall-server-from-hc` workflow (`docs/ecosystem/notes/workflows.md`
§1a.6). It:

- checks membership and takes server-scan's lock;
- deletes the node's Machine and waits for the drain;
- verifies what is left;
- removes the server from the MCE, then releases the lock.

Every refusal after the start is a FAILED run whose error names the reason,
for example `ClusterMembershipMismatchError`.

The user asked for each cluster's nodes and an Uninstall button. The user
decided (2026-11-11) that **Wingman starts the workflow and shows its run;
the procedure and its checks are the workflow's.** The orchestrator has no
auth and no field for who asked.

## Decision

- **Two ports**, each with an httpx adapter and a fake (ADR-0001, ADR-0019).
  Their calls are counted as the `server_scan` and `workflows` dependencies
  (`docs/ops/metrics.md`).
  - `ServerInventory` is server-scan: the fleet's rows, and one server.
  - `UninstallWorkflow` is the orchestrator: its run list, one run, and a
    start.
- **Nodes** are the rows whose `cluster_name` is either of the cluster's
  names, one per server id, sorted by name.
  - Day1 reads the whole fleet once (`GET /api/v1/servers/rows`) and picks
    each cluster's rows from it, so a page that shows many clusters costs one
    read. The rows are cached per replica for `DAY1_CACHE_TTL_SECONDS`
    (ADR-0011) and revalidated with their `ETag`.
- **Runs** come from one cached list of the fleet's 200 newest uninstall runs.
  - A node's run is found by the workflow's deterministic id,
    `uninstall-server-from-hc-<name lowercased>`. A node that server-scan
    shows held by the uninstall's lock counts too, even when the list misses
    its run.
  - Each matched run is read once more, cached for at most 10 s, for its step
    and error.
  - The status is lowercased; the phase and error are the workflow's own
    strings, passed through. Day1 keeps no list of phases.
  - When the orchestrator cannot be read, the nodes are still listed, with
    `runs_error` set.
- **Uninstall** is for admins only.
  - The node's name must be typed again; it is compared ignoring case.
  - Day1 reads the server fresh (`GET /api/v1/servers/{id}`) and checks one
    thing: server-scan places it in this cluster under either name. If not,
    it refuses with 409 `NODE_NOT_IN_CLUSTER`. That check makes the button act
    on what the page showed.
  - Nothing else is checked: the MCE, a contested claim, maintenance and
    another run's lock are the workflow's checks.
  - Day1 starts the run with `server_names` set to the one name and
    `mce_cluster` set to the cluster's MCE folder. It adds `namespace` only
    when `MCE_INFRAENV_NAMESPACE` is set.
  - It logs who started the run as a structured event,
    `node_uninstall_started`.
- **A start is a write and is never retried** (ADR-0006). What happened to it
  decides the answer:
  - Refused before it was sent (no connection), refused by the orchestrator
    (a 422, or its 502 when Temporal refuses), or any other 5xx but a
    gateway's 504: 502 `DEPENDENCY_UNAVAILABLE`, nothing started.
  - Sent without an answer (a read timeout, a dropped connection, a gateway's
    504, a 202 whose body cannot be read): 504 `AMBIGUOUS_WRITE`, and the
    detail says to look at the node's run before trying again.
  - The orchestrator's 409: 409 `UNINSTALL_ALREADY_RUNNING`.
  - Whatever the answer, the cached runs are dropped, so the next read sees
    the run if there is one.
- **Off by default.**
  - With `SERVER_SCAN_URL` empty, both routes answer 501 `FEATURE_DISABLED`.
  - With `WORKFLOWS_API_URL` empty, the start answers 501, and the nodes
    answer says `uninstall.available: false` with the reason.
  - `WORKFLOWS_API_URL` without `SERVER_SCAN_URL` refuses to start (ADR-0009).
  - The viewer token comes from an existing Secret, through the chart's
    `serverScan.tokenSecret`.
- **`DAY1_FAKE_FLEET=true`** replaces both systems with fakes seeded from
  `dev/fleet-fixtures/servers.yaml`, in server-scan's own row shape. It is
  refused unless `WINGMAN_ENVIRONMENT=development`.
- The routes, bodies and errors are in
  `docs/notes/2026-11-11-cluster-nodes-api.md`.

## Alternatives rejected

- **Checking the MCE, a contested claim, maintenance or a held lock before
  starting.** The workflow makes these checks against the MCE itself and
  reports a refusal as a failed run with its reason. A second copy in
  Wingman would drift from the procedure and could refuse what the workflow
  accepts, or the reverse.
- **`GET /api/v1/servers?cluster_name=` per cluster.** It takes one name per
  call, so it costs two calls per cluster and grows with the page.
- **Nodes from the MCE hub's Agents.** That needs the per-MCE Kubernetes
  clients of `CLUSTER_STATUS_ENABLED`. server-scan already ties hardware and
  health to clusters.
- **Reading every node's run.** That is one call per node, mostly for nodes
  that never ran.
- **Calling the orchestrator from the browser.** It has no auth and no CORS.
  Day1 is its only caller from Wingman, for admins only.

## Consequences

- An empty node list means server-scan places no server in the cluster. A
  cluster whose `nodes-status` job does not run shows none.
- After a completed uninstall, the server leaves the list once the cached
  rows expire.
- The run list holds the fleet's 200 newest runs. An older run that is still
  running is found through server-scan's lock; an older finished one is no
  longer shown.
- The orchestrator answers `[]` for an unknown workflow type, so the class
  name `UninstallServerFromHcWorkflow` (from the notes) cannot be checked
  live. A renamed class would show no runs, not an error.
- The workflow's phases can change without a Wingman change.
- Who started a run is recorded only in day1's log.
- The web matches two new codes, both 409: `NODE_NOT_IN_CLUSTER` and
  `UNINSTALL_ALREADY_RUNNING`.

## Verification

- `apps/day1-service/tests/unit/domain/test_servers.py`: which servers are
  nodes, and which have a run.
- `tests/unit/application/test_nodes.py`, on the fakes through
  `create_app`'s caches:
  - the runs merge and `runs_error`;
  - every refusal, and the fresh read;
  - what is left to the workflow;
  - the ambiguous start and the log events.
- `tests/unit/infrastructure/test_server_scan.py` and
  `test_workflows_api.py`, against `httpx.MockTransport` with the live shapes
  (read by GET only, 2026-11-11). They include the request schema of the
  saved OpenAPI document, `docs/ecosystem/notes/workflows-orchestrator-openapi.json`.
- `tests/unit/infrastructure/test_fake_fleet.py`: the fixture fits the
  fixture clusters, and the fake run walks.
- `tests/api/test_nodes_api.py`: the contract's shapes and codes.
- `tests/unit/test_settings.py` and `tests/unit/test_main.py`.
- `tests/repo/test_chart_env_contract.py`: the chart's variables, the token
  from its Secret included.
