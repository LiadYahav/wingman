# Scaling NodePools through the update-nodepool workflow (2026-11-16)

The platform has a Temporal workflow that sets how many workers a hosted
cluster runs: `update-nodepool`, started through the workflows orchestrator.
Wingman starts it from the cluster page's Nodes tab and shows its run there
(ADR-0062). This note is the contract between day1 and the web. Wingman only
starts a run and shows it: the plan, its checks and its phase list are the
workflow's (the rule of ADR-0038, ADR-0042 and ADR-0055).

Source: `team-redbull/workflows`, branch `feat/update-nodepool` (not merged,
no PR yet): `workflow_domains/server_lifecycle/router.py`
(`UpdateNodePoolRequest`, `start_update_nodepool`),
`workflow_domains/server_lifecycle/update_nodepool.py`,
`shared/models/server_lifecycle.py` (`UpdateNodePoolInput`,
`NodePoolProgress`, `UpdateNodePoolResult`, `NodePoolScaleResult`,
`ScaleDownChoice`), `shared/exceptions.py`, `shared/workflow_ids.py`,
`workflow_domains/routers/runs.py` and the design page
`docs/site/server-lifecycle/update-nodepool.html`. The branch can still
change: day1 reads its answers leniently. Last matched: b1976f4 and
aab8949 (2026-11-18: one NodePool a run, ADR-0062's 2026-11-18 amendment).

## 1. What the workflow takes and does

**Start:** `POST /workflows/server-lifecycle/update-nodepool`, JSON
(`extra="forbid"`): `mce_cluster` (with or without `ocp4-`), `cluster` (the
day1 file's name without `.yaml`, a Kubernetes name), `nodepool` (one
NodePool of the cluster, by name, a Kubernetes name) and `replicas` (≥ 0,
that NodePool's own, set exactly; its siblings are left as they are), and
on a scale-down, at most one of (both are a 422):
- `server_names`, the servers that leave: one name or a list of up to 20,
  each once (case-insensitively), as many as the replicas removed, each a
  Machine of the NodePool;
- `scale_down_policy`, a policy for this run only (`fewest-pods`,
  `least-requested` or `least-utilized`; any other is a 422), ranked ahead of
  the NodePool's own `redbull.io/scale-down-policy`, even one of its own that
  is no policy.

A scale-up or no change ignores both and lists them in the result's
`ignored`. Day1 sends these, and either of the last two only on a
scale-down. `infra_env_kind` (until 2026-11-18 a TOTAL over
the cluster's NodePools of one InfraEnv kind) is a 422 that says to name the
NodePool; a run recorded with it before then still finishes as it began.
Answers `202 {"workflow_id": "update-nodepool-<cluster>", "run_id"}`; 409
while a run of the cluster runs, and while `upgrade-cluster-<cluster>` runs
(its `detail` says which); 422 for a body it refuses. Never a 404: an
unknown cluster or NodePool is a FAILED run. An orchestrator without the
workflow (not deployed yet) answers FastAPI's 404 for a path it has no route
for, whose whole body is `{"detail": "Not Found"}` (ADR-0062's 2026-11-19
amendment).

**What it does:** reads the cluster file in day1 `main` and the NodePool on
the MCE (they must agree, both ways), plans, and through its child
(`scale-up-nodepool-<cluster>` or `scale-down-nodepool-<cluster>`) commits
only that `replicas:` line to day1 `main`, syncs the cluster's Argo CD
Application to that commit, and checks that the NodePool shows the
replicas. On a scale-down the servers that leave are, in this order: the
`server_names` sent; else those a policy ranks first, the request's
`scale_down_policy`, else the NodePool's own `redbull.io/scale-down-policy`
label or annotation (`fewest-pods` the fewest workload pods,
`least-requested` the lowest requested CPU or memory share, `least-utilized`
the lowest live use, from the hosted cluster's `metrics.k8s.io`: without it
the run fails, `NodeMetricsUnavailableError`); with neither, CAPI picks at
random. Under every policy CAPI-unhealthy Machines go first (on OpenShift
4.18's CAPI a marked and an unhealthy Machine rank the same, so a policy
takes the unhealthy ones first, in CAPI's order). Freed servers stay in the
MCE's inventory. Done
means the NodePools show the replicas, not that new nodes are Ready.

**The run:** `GET /workflows/runs/{id}` (404: none) answers
`{workflow_id, workflow_type, status, progress?, result?, error?}`.
`progress` (while running, and after a failure) is `{phase, direction,
child_workflow_id}`; the child has no route of its own, its phase is read
the same way by its id. Phases today: parent `pending → reading-day1 →
reading-nodepools → planning → scaling-up | scaling-down → completed`;
scale-up `pending → committing-day1 → syncing-argo → verifying-nodepools →
completed`; scale-down `pending → [selecting-servers → marking-machines] →
committing-day1 [→ unmarking-machines] → syncing-argo → verifying-nodepools
[→ verifying-machines] → completed`. Wingman keeps no list of them.
`result` (`UpdateNodePoolResult`) has the NodePool before and after (a run
recorded by kind: the kind's NodePools, and `infra_env_kind` set instead of
`nodepool`), `ignored` (since 2026-11-18: what the request said about a
scale-down that a run scaling up, or not at all, had no use for, each with why,
in the workflow's words; never a failure) and, in `scale`, the child's
commit, the NodePools read back, the servers chosen and those seen
deleting (a named server's `chosen` entry has `policy: "named"`, `reason:
"named: <name>"` and `server`, lowercased). A new failure type,
`ScaleDownServersInvalidError`: the servers a scale-down request named cannot
be the ones that leave, nothing marked or written. The workflow matches a
named server to its Machine by AgentMachine → Agent → the Agent's
`agent-install.openshift.io/bmh` label, else its hostname, else the
Machine's Node (lowercased), and refuses a wrong count, a server no Machine
of the NodePool is (or two are), an unnamed CAPI-unhealthy Machine that
OpenShift 4.18's CAPI would take instead, and an MCE worker too old to say
which server a Machine is. Named servers are documented for OpenShift 4.19
and later. `error` is the root failure's message only: a
child's failure reads `<child id> failed — <Type>: <message>`; the parent's
own refusals name no type.

## 2. Day1's routes

All under `/api/day1/clusters/{name}`, with the page's `?site=&mce=`. `501
FEATURE_DISABLED` on all three while `DAY1_SCALE_NODEPOOLS` is off.

**`GET .../scale`** (any signed-in user): what Scale offers (the Nodes tab's
steppers, ADR-0062's amendments), from the cluster file on `main`, so it
works without live status.

```json
{ "cluster": "ocp4-prod-lark-site1", "mce": "ocp4-prod-mce-site1-a", "flavor": "agent-sized",
  "nodepools": [ { "index": 0, "name": "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb",
                   "infra_env": "dell-r660-site1-128c-1024gb-5tb", "replicas": 3,
                   "locked_by": "agent-sized", "locked_replicas": 3, "unnamed": null,
                   "scale_down_policy": "fewest-pods" } ] }
```

- `name` is the chart's (`name`, else `<clusterName>-<infraEnvName>`, else
  `<clusterName>-<agentLabelSelector.nodeLabelValue>`), the name the
  workflow matches day1 with the MCE by; `null` with `unnamed` saying why.
- `replicas` is the file's (1 when absent, the chart's default; `null` when
  not a whole number). `locked_by`/`locked_replicas`: the cluster's flavor
  locks `nodepools[<index>].replicas`.
- `scale_down_policy` (2026-11-16, 3.42.0): the entry's
  `annotations["redbull.io/scale-down-policy"]` as written, which the
  hostedclusters-setup chart renders onto the NodePool; `null` without one.
  Not checked: the workflow refuses a value other than `fewest-pods`,
  `least-requested` and `least-utilized`, and the web says so before the
  run. A label or annotation set by hand on the MCE's NodePool (the
  air-gapped chart copy renders no entry annotations yet) is not in the file:
  the run reads it, and its result's `scale_down_policy` shows what it used.
  The scale confirmation says which nodes leave from it.
- No `kinds` since 2026-11-18: a run sets one NodePool.

**`POST .../scale`** (admin), `{"nodepool": "...", "replicas": N}`, a
Kubernetes name, `N` 0-10000, and on a scale-down, optionally,
`"server_names": ["<server>", ...]` (1 to 20 server names, each once,
case-insensitively): exactly the servers that leave, or
`"scale_down_policy": "fewest-pods" | "least-requested" | "least-utilized"`
(2026-11-18, later): which servers leave, for this run only, ahead of the
NodePool's own policy. No other field. Day1
adds `mce_cluster` (the file's MCE folder) and `cluster` (the file stem).
`202` with the run (`status: "running"`). The names to send are the
NodePool's nodes' `machine_server` in `GET .../nodes` (2026-11-11 note):
the workflow's own rule, so they match.
- `422 VALIDATION_ERROR`: the body (`infra_env_kind` in words: send the
  NodePool's name as `nodepool`); a `nodepool` no entry of the file on
  `main` renders (the problem lists the file's NodePools) or two entries
  render; a NodePool a flavor locks, to anything but its locked value;
  `server_names` on anything but a scale-down of the file's replicas on
  `main`, or not exactly as many as it removes (the problem says how many
  leave); `scale_down_policy` that is not one of the three, beside
  `server_names`, or on anything but a scale-down. Nothing is sent. Which Machine each named server is stays the
  workflow's to judge: a failed run, `ScaleDownServersInvalidError`. The orchestrator's own 422 is the same code, with its
  findings, and "nothing was started".
- `409 SCALE_ALREADY_RUNNING`: the orchestrator's 409, its words in
  `detail`.
- `504 AMBIGUOUS_WRITE`: sent, no answer; it may have started. Read the run
  first; never retried.
- `502 DEPENDENCY_UNAVAILABLE`: the orchestrator could not be reached or
  refused otherwise; nothing started. An orchestrator without
  update-nodepool (FastAPI's 404 above) is this too, in these words:
  "update-nodepool is not deployed on this orchestrator yet (it has no POST
  /workflows/server-lifecycle/update-nodepool): nothing was started for
  <cluster>. Scaling works as soon as the workflow is deployed there, with
  no change to Wingman." Any other 404 is a refusal in the orchestrator's
  words. Meanwhile `GET .../scale` works and `GET .../scale-run` is `404
  NOT_FOUND` (no run).

**`GET .../scale-run`** (any signed-in user): the cluster's newest run, `404
NOT_FOUND` when it never had one.

```json
{ "workflow_id": "update-nodepool-ocp4-prod-lark-site1", "status": "running",
  "phase": "scaling-down", "direction": "down",
  "child": { "workflow_id": "scale-down-nodepool-ocp4-prod-lark-site1", "status": "running",
             "phase": "marking-machines", "error": null },
  "result": null, "error": null, "error_type": null }
```

Completed, `result` is `{infra_env_kind, nodepool, day1_path, direction,
total_before, total_after, nodepools: [{name, infra_env, before, after,
scale_down_policy}], child_workflow_id, revision, committed, live: [{name,
replicas, ready_replicas}], chosen: [{nodepool, machine, node, policy,
reason, server}], deleting: [machine], ignored: [text]}` (`server` set on a
named server, else `null`; a NodePool's `scale_down_policy` is the policy the
run applied, the request's or the NodePool's own, and `null` when it named
its servers or had none); `infra_env_kind` only on
a run recorded by kind before 2026-11-18, `nodepool` on every other. Failed, `error` is the workflow's words and
`error_type` the type when they name one (`ArgoSyncRefusedError`), else
`null`; `child` is read while the parent names it and has no result.

## 3. Replicas while scaling is on

- `PATCH /clusters/{name}` and `PUT /approvals/{iid}`: a write that changes
  the `replicas` of a NodePool on `main` (a review edit is compared with
  the target branch) is `422 VALIDATION_ERROR` with
  `nodepool <name> replicas: 3 → 4. NodePool replicas change through Scale
  on the cluster's Nodes tab`. A new cluster, a new entry with its first
  replicas, and a removed entry are not refused.
- `POST /clusters/{name}/sync/preview` and `POST /clusters/{name}/sync`:
  `held_replicas: [{index, name, replicas, flavor_replicas}]`, the drifted
  locked replicas the MR leaves out (`[]` when off). The sync's answer is
  the MR, with `held_replicas` beside it. A restore is `POST .../scale`
  `{"nodepool": name, "replicas": flavor_replicas}`.
- `GET|POST /specs/{name}/rollout`: each cluster's item has
  `held_replicas`, the same shape, for its pending MR.
