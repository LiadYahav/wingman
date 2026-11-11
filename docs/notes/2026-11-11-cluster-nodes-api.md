# Cluster nodes and node uninstall: the API the web reads (2026-11-11)

What day1 adds so the web can show the servers under each hosted cluster
(from server-scan) and start the platform's `uninstall-server-from-hc`
workflow on one of them. Wingman only starts the workflow and shows its
run: the procedure (drain, lock, removal, and the checks before them) is
the workflow's, and Wingman neither repeats nor second-guesses it. Decision and reasons: ADR-0038. Background:
`docs/ecosystem/notes/server-scan.md` §7 and `docs/ecosystem/notes/workflows.md`
§1a.6 and §2.

## 1. The nodes of a cluster

`GET /api/day1/clusters/{name}/nodes?site=&mce=`, any signed-in user.

A node is a server-scan server whose `cluster_name` is this cluster's
HostedCluster (`ocp4-<clusterName>`) or its bare `clusterName`. The server
`cluster_name` comes from the `nodes-status` jobs, and the two names cover
both of its writers. Day1 reads server-scan's whole fleet once
(`GET /api/v1/servers/rows`), caches it, and picks the cluster's rows, so a
list page that expands many clusters costs one read.

```json
{
  "hosted_cluster": "ocp4-prod-lark-site1",
  "nodes": [
    {
      "id": "srv_0d48131a4fcc4b4c9cc8eec6ef72c421",
      "name": "ocp-dell-r660-site1-64c-512gb-DL0000123",
      "url": "https://server-scan.example/servers/srv_0d48131a4fcc4b4c9cc8eec6ef72c421",
      "serial": "DL0000123",
      "vendor": "dell",
      "model": "PowerEdge R660",
      "site": "site1",
      "mce": "ocp4-prod-mce-site1-a",
      "state": "INSTALLED",
      "health": "HEALTHY",
      "maintenance": false,
      "reachable": true,
      "stale": false,
      "contested": false,
      "last_seen_at": "2026-11-11T08:00:03Z",
      "uninstall": null
    }
  ],
  "uninstall": {"available": true, "detail": null},
  "runs_error": null
}
```

- `nodes` are sorted by `name`. An empty list means server-scan places no
  server in this cluster; it never stands for "server-scan could not be
  read" (that is a 503, below).
- `url` is the server's page in server-scan's UI (`<SERVER_SCAN_UI_URL>/servers/<id>`).
- `state` is server-scan's `openshift_state` (`INSTALLED`,
  `INSTALLED_TO_INVENTORY`, `AVAILABLE`); `health` its overall verdict
  (`HEALTHY`, `WARNING`, `MAJOR`, `CRITICAL`, `UNKNOWN`; `UNKNOWN` is not a
  verdict); `serial`, `vendor`, `model`, `mce` and `last_seen_at` may be
  `null`.
- `contested` means two clusters' jobs claim the server (server-scan's
  `contested_with`). It is shown, nothing more: the workflow refuses a
  contested server itself.
- `uninstall` is the node's newest uninstall run, or `null`:
  `{"workflow_id", "status", "phase", "error"}`. `status` is the
  orchestrator's, lowercase (`running`, `completed`, `failed`, `canceled`,
  `terminated`, `timed_out`). `phase` is the run's step while it runs, the
  workflow's own string, passed through (`checking-inventory`,
  `awaiting-machine-deletion`, ...); Wingman keeps no list of them. `error` is
  the orchestrator's message when it failed (it names the error type, e.g.
  `ServerReservedError: ...`).
- `uninstall.available` (top level) is `false` when the orchestrator is not
  configured; `detail` then says so, and the web shows no Uninstall button.
- `runs_error` is set when the orchestrator could not be read: the nodes
  are still listed, every `uninstall` is `null`, and run states are
  unknown, not "none".

Errors (RFC 9457, ADR-0004):

| Status | `code` | When |
|---|---|---|
| 404 | `NOT_FOUND` | No such cluster. |
| 501 | `FEATURE_DISABLED` | server-scan is not configured (`SERVER_SCAN_URL` empty). |
| 503 | `DEPENDENCY_UNAVAILABLE` | server-scan did not answer, or answered with an error. |

## 2. Uninstall one node

`POST /api/day1/clusters/{name}/nodes/{server_id}/uninstall?site=&mce=`,
admins only.

```json
{"server_name": "ocp-dell-r660-site1-64c-512gb-DL0000123"}
```

`server_name` is the node's name typed again (compared case-insensitively),
because the uninstall cannot be undone. Day1 reads the server from
server-scan, fresh rather than from the cache, to check that it is one of
this cluster's nodes, so the button acts on what the page showed. It
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
| 409 | `NODE_NOT_IN_CLUSTER` | server-scan does not place the server in this cluster. |
| 409 | `UNINSTALL_ALREADY_RUNNING` | The orchestrator already runs an uninstall of this server. |
| 422 | `VALIDATION_ERROR` | `server_name` is not the server's name. |
| 501 | `FEATURE_DISABLED` | server-scan or the orchestrator is not configured. |
| 503 | `DEPENDENCY_UNAVAILABLE` | server-scan or the orchestrator refused or could not be reached; nothing started. |
| 502 | `AMBIGUOUS_WRITE` | The start was sent but no answer came back: it may have started. Look at the node's run before trying again; never retried (ADR-0006). |

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
| `DAY1_FAKE_FLEET` | `false` | Development only (refused otherwise): an in-memory server-scan and orchestrator seeded from `dev/fleet-fixtures/`. An uninstall walks through the real phases and frees the server. |
