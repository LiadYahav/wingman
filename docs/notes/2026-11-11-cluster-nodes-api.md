# Cluster nodes by NodePool, and node uninstall: the API the web reads (2026-11-11)

What day1 adds so the cluster page can show each NodePool's nodes: what is
there, what is missing and why, and which node an update is working on. It
also lets an admin start the platform's `uninstall-server-from-hc`
workflow on one of them. Wingman only starts the workflow and shows its
run: the procedure (drain, lock, removal, and the checks before them) is
the workflow's, and Wingman neither repeats nor second-guesses it. Decision and reasons: ADR-0038. Background:
`docs/ecosystem/notes/server-scan.md` §7 and `docs/ecosystem/notes/workflows.md`
§1a.6 and §2.

## 1. The nodes of a cluster, by NodePool

`GET /api/day1/clusters/{name}/nodes?site=&mce=`, any signed-in user. The
cluster page's Nodes tab reads it; nothing else does (the cluster list shows
no nodes).

The NodePools and their Machines come from the cluster's MCE, read-only,
through the same hub access as live status (`CLUSTER_STATUS_ENABLED`). Each
Machine is followed to its server: Machine `spec.infrastructureRef` →
AgentMachine `status.agentRef` → Agent label `agent-install.openshift.io/bmh`
→ BareMetalHost name, which is server-scan's server name (MAC or serial when
the label is missing). server-scan adds the link and the health. What the
hub does and does not say, with sources:
`docs/ecosystem/notes/hypershift-node-state.md`.

```json
{
  "hosted_cluster": "ocp4-prod-lark-site1",
  "node_pools": [
    {
      "name": "prod-lark-site1-dell-r660-site1",
      "wanted": 3,
      "autoscaling": null,
      "ready": 2,
      "version": "4.18.22",
      "upgrade_type": "InPlace",
      "agent_selector": "infraenvs.agent-install.openshift.io=dell-r660-site1",
      "update": {
        "kind": "version",
        "message": "Nodepool update in progress. Target Config version: 6c1f2b. Total Nodes: 3. Upgraded: 1",
        "progress": {"total": 3, "updated": 1},
        "failed": false
      },
      "problems": ["AllNodesHealthy: Machine prod-lark-site1-dell-r660-site1-x7k2p: NodeConditionsFailed"],
      "free_agents": {"matching": 4, "free": 0},
      "nodes": [
        {
          "machine": "prod-lark-site1-dell-r660-site1-x7k2p",
          "node_name": "worker-2",
          "state": "not_ready",
          "current": true,
          "activity": "Rebooting for the update (Node condition Ready is Unknown)",
          "waiting_for": null,
          "outdated": null,
          "agent": {"name": "5f0c…", "state": "added-to-existing-cluster", "stage": "Done"},
          "server_name": "ocp-dell-r660-site1-64c-512gb-DL0000123",
          "server": {
            "id": "srv_0d48131a4fcc4b4c9cc8eec6ef72c421",
            "name": "ocp-dell-r660-site1-64c-512gb-DL0000123",
            "url": "https://server-scan.example/servers/srv_0d48131a4fcc4b4c9cc8eec6ef72c421",
            "serial": "DL0000123", "vendor": "dell", "model": "PowerEdge R660",
            "site": "site1", "mce": "ocp4-prod-mce-site1-a", "state": "INSTALLED",
            "health": "HEALTHY", "maintenance": false, "reachable": true, "stale": false,
            "contested": false, "last_seen_at": "2026-11-11T08:00:03+00:00"
          },
          "uninstall": null
        },
        {
          "machine": "prod-lark-site1-dell-r660-site1-q9w4m",
          "node_name": null,
          "state": "waiting",
          "current": false,
          "activity": null,
          "waiting_for": "No free Agent matches this NodePool: 4 Agents match its selector, none is free (3 bound, 1 not approved)",
          "outdated": null,
          "agent": null,
          "server_name": null,
          "server": null,
          "uninstall": null
        }
      ]
    }
  ],
  "unassigned": [ { "...": "a server object as above, plus \"uninstall\"" } ],
  "uninstall": {"available": true, "detail": null},
  "server_scan_error": null,
  "runs_error": null
}
```

**A NodePool**
- `wanted` is `spec.replicas` (`null` when it autoscales; `autoscaling` is
  then `{"min", "max"}`). `ready` is `status.replicas`. `version` is
  `status.version`, the version it last finished updating to.
- `upgrade_type` is `InPlace`, `Replace` or `null`. `agent_selector` is its
  `agentLabelSelector` in words, or `null`.
- `update` is `null` unless `UpdatingVersion`, `UpdatingConfig` or
  `UpdatingPlatformMachineTemplate` is not False. `kind` is `version`, `config`
  or `machine_template`; `message` is the condition's own text, passed
  through; `progress` is parsed from `Total Nodes: n. Upgraded: k` when an
  in-place update says it (the condition, or the MachineSet annotation on
  older MCEs), else `null`; `failed` is true on `InplaceUpgradeFailed`.
- `problems` are the NodePool's `Ready`, `AllMachinesReady` and
  `AllNodesHealthy` conditions that are not True, as `"<Type>: <reason>:
  <message>"` (empty parts left out), passed through.
- `free_agents` counts the Agents in the cluster's agent namespace that
  match its selector, and how many of them are free by the Agent provider's
  rule (no `agentMachineRef` label, approved, Validated, Connected, not
  Bound). `null` when the Agents could not be counted.
- NodePools are sorted by name; nodes by state (`failed`, `deleting`,
  `waiting`, `missing`, `installing`, `joining`, `not_ready`, then `ready`),
  then by server name or Machine name.

**A node** is one Machine of the pool (or a missing one).
- `state`, derived in this order:
  - `deleting`: the Machine has a deletion timestamp.
  - `failed`: the Machine's phase is `Failed`, or it is the node an in-place
    update names as degraded.
  - `waiting`: no Agent is reserved for it (`AgentReserved` not True).
    `waiting_for` says why, from the reason and `free_agents`.
  - `installing`: an Agent is reserved but not installed.
  - `joining`: installed, no Node yet (`status.nodeRef` empty).
  - `not_ready`: the Node exists but `NodeHealthy` is not True.
  - `ready`: otherwise.
  - `missing`: not a Machine. The pool wants more than it has non-deleting
    Machines, and one such row stands for each missing one (`machine` is
    `null`).
- `activity` says in words what is happening to it now, or `null`:
  - "Draining", "Waiting for volumes to detach", "Waiting for the host to
    return to discovery" (deleting; from the first unmet deletion
    condition, or v1beta2 `Deleting`);
  - "Installing: Writing image to disk" (the Agent's stage);
  - "Joining the cluster";
  - "Rebooting for the update (…)" (`not_ready` while the pool updates in
    place), "Node not ready: …" otherwise;
  - the degraded reason for a `failed` in-place node.
- `current` is true for the node being worked on right now:
  - **InPlace:** a `not_ready` node while the pool updates, and the degraded
    one. The hub does not show the drain before the reboot, nor which node
    the update will take next.
  - **Replace:** every Machine that is `deleting`, `installing`, `joining`
    or `waiting` while the pool updates.
- `outdated` (Replace only) is true for a Machine of an older MachineSet
  revision, which the rollout will replace; `null` for InPlace.
- `agent` is `{"name", "state", "stage"}`: the Agent's `debugInfo.state` and
  `progress.currentStage`, or `null`.
- `server_name` is the BareMetalHost name (`null` with no Agent). `server` is
  server-scan's record of it (as in the example), or `null` when server-scan
  has none or is not configured.
- `uninstall` is the server's newest uninstall run, or `null`:
  `{"workflow_id", "status", "phase", "error"}`.
  - `status` is the orchestrator's, lowercase (`running`, `completed`,
    `failed`, `canceled`, `terminated`, `timed_out`).
  - `phase` is the workflow's own string, passed through; Wingman keeps no
    list of them.
  - `error` is the orchestrator's message when it failed.

**The rest**
- `unassigned`: servers server-scan places in this cluster (by its
  `cluster_name`: the HostedCluster or the bare `clusterName`) that no
  Machine leads to. That happens for a few minutes after an uninstall, or
  with what a broken node deletion left behind. Each is the `server` shape
  plus `uninstall`.
- `uninstall.available` is `false` when the orchestrator or server-scan is
  not configured; `detail` then says so.
- `server_scan_error` is set when server-scan could not be read. The nodes
  are still listed, with `server: null`, and `unassigned` is empty.
- `runs_error` is set when the orchestrator could not be read. Every
  `uninstall` is then `null`, which means unknown, not "none".

Errors (RFC 9457, ADR-0004):

| Status | `code` | When |
|---|---|---|
| 404 | `NOT_FOUND` | No such cluster. |
| 501 | `FEATURE_DISABLED` | The MCE cannot be read: live status is off (`CLUSTER_STATUS_ENABLED`). |
| 502 | `DEPENDENCY_UNAVAILABLE` | The MCE did not answer, or answered with an error. |

## 2. Uninstall one node

`POST /api/day1/clusters/{name}/nodes/{server_id}/uninstall?site=&mce=`,
admins only.

```json
{"server_name": "ocp-dell-r660-site1-64c-512gb-DL0000123"}
```

`server_name` is the node's name typed again (compared case-insensitively),
because the uninstall cannot be undone. Day1 reads the server from
server-scan, fresh rather than from the cache, to check that it is one of
this cluster's nodes: a Machine of the cluster leads to it, or server-scan
places it in the cluster. So the button acts on what the page showed. It
checks nothing else: the workflow does its own checks. It then starts it with
`{"server_names": "<name>", "mce_cluster": "<the cluster's MCE>"}` (plus
`namespace` when `MCE_INFRAENV_NAMESPACE` is set), and logs who started it.

202:

```json
{"workflow_id": "uninstall-server-from-hc-ocp-dell-r660-site1-64c-512gb-dl0000123",
 "status": "running", "phase": null, "error": null}
```

What the run does, for a short summary in the confirmation dialog (the
workflow's documentation is the authority):
- It drains the node and deletes its Machine.
- The server leaves the hosted cluster, then the MCE: powered off, and its
  BareMetalHost and Agent removed. It is free in server-scan afterwards.
- The NodePool's replicas are never changed, so the NodePool binds a
  replacement node. This is a replacement, not a shrink.
- Nothing is undone on failure; a re-run resumes.

Most refusals happen inside the run: it fails, and its `error` says why.

| Status | `code` | When |
|---|---|---|
| 404 | `NOT_FOUND` | No such cluster, or no such server in server-scan. |
| 409 | `NODE_NOT_IN_CLUSTER` | Neither a Machine of the cluster nor server-scan places the server in this cluster. |
| 409 | `UNINSTALL_ALREADY_RUNNING` | The orchestrator already runs an uninstall of this server. |
| 422 | `VALIDATION_ERROR` | `server_name` is not the server's name. |
| 501 | `FEATURE_DISABLED` | server-scan or the orchestrator is not configured. |
| 502 | `DEPENDENCY_UNAVAILABLE` | server-scan or the orchestrator refused or could not be reached; nothing started. |
| 504 | `AMBIGUOUS_WRITE` | The start was sent but no answer came back: it may have started. Look at the node's run before trying again; never retried (ADR-0006). |

## 3. Settings (day1)

| Variable | Default | Meaning |
|---|---|---|
| `SERVER_SCAN_URL` | empty (off) | server-scan's API base, e.g. `http://server-scan-api.<ns>.svc:8000`. |
| `SERVER_SCAN_UI_URL` | `SERVER_SCAN_URL` | Where the node links point: server-scan's UI. |
| `SERVER_SCAN_TOKEN` | empty | A server-scan viewer token (`Authorization: Bearer`), from a Secret. Empty: no header, for an instance with auth off. |
| `SERVER_SCAN_SSL_VERIFY` | `true` | `true`, `false` or a CA bundle path. |
| `SERVER_SCAN_TIMEOUT_SECONDS` | `10` | Per request. The fleet read is about 250 KB gzipped for 3,000 servers. |
| `WORKFLOWS_API_URL` | empty (off) | The orchestrator, e.g. `http://workflows-orchestrator-api.<ns>.svc:8080`. It has no auth: day1 is its only caller from Wingman, admins only. |
| `WORKFLOWS_SSL_VERIFY` | `true` | As above. |
| `WORKFLOWS_TIMEOUT_SECONDS` | `10` | Per request. |
| `DAY1_FAKE_FLEET` | `false` | Development only (refused otherwise): an in-memory server-scan, orchestrator and MCE (NodePools, Machines, AgentMachines, Agents) seeded from `dev/fleet-fixtures/`. An uninstall walks through a few sample phases, frees the server, and the NodePool's replacement Machine then waits for a free Agent. |

## 4. What the MCE token must be allowed to read

The nodes view reads more of the MCE than live status did. The service
account behind each MCE token needs `get` and `list` on:

| API group | Resources | Namespace |
|---|---|---|
| `hypershift.openshift.io` | `hostedclusters`, `nodepools` | `hcp-<clusterName>` |
| `cluster.x-k8s.io` | `machines`, `machinesets` | the control-plane namespace `hcp-<clusterName>-ocp4-<clusterName>` |
| `capi-provider.agent-install.openshift.io` | `agentmachines` | the control-plane namespace |
| `agent-install.openshift.io` | `agents`, `infraenvs` | the HostedCluster's agent namespace (`spec.platform.agent.agentNamespace`) |

Control-plane namespaces are created per cluster, so a ClusterRole with a
ClusterRoleBinding is the simple grant. No Secrets: Wingman never reads a
hosted cluster's own API.

## 5. The segments-manager link

`GET /api/day1/clusters/{name}` gains one field, read by the Overview's
**HostedCluster & network** card:

```json
"segments_manager": {
  "url": "https://segments-manager.example/",
  "search_url": "https://segments-manager.example/api/segments/search?q=ocp4-prod-lark-site1"
}
```

It is `null` unless day1's `SEGMENTS_MANAGER_UI_URL` is set (chart:
`segmentsManager.uiUrl`; empty by default). Day1 builds both URLs and never
calls segments-manager; the web never assembles them itself.

segments-manager's UI reads no URL parameters, so no link opens one
cluster's segment: `url` opens the UI, and the card names the cluster to
search for there, with a copy button. `search_url` is its open
`GET /api/segments/search?q=`, the matching segments as JSON. Both search by
the cluster's `name`, the file stem, because that is the `cluster_name`
allocate-segment gives segments-manager
(`docs/ecosystem/notes/segments-manager.md` §4, §5), not the chart's
`clusterName`. The search matches substrings, so it may also list a cluster
whose name contains this one (`<name>-b`).

| Variable | Default | Meaning |
|---|---|---|
| `SEGMENTS_MANAGER_UI_URL` | empty (off) | segments-manager's UI, e.g. `https://segments-manager.example`. The browser opens it; day1 does not. |

## 6. Live status: an update is not a problem

`GET /api/day1/clusters/{name}/status` (and the bulk and stream reads)
used to list a NodePool's `UpdatingVersion=True` or `UpdatingConfig=True`
as a problem, so a normal rollout showed red. Each node pool now carries
`updating` (`"version"`, `"config"`, `"machine_template"` or `null`), and
only a failed in-place update (reason `InplaceUpgradeFailed`) is a problem,
as `"<Type>: InplaceUpgradeFailed: <message>"`. The cluster page shows each
pool's live state in the Nodepools card ("2 / 3 ready · Updating config");
the Live Status card keeps the HostedCluster's version and health.
