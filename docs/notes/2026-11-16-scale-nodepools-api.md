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
change: day1 reads its answers leniently.

## 1. What the workflow takes and does

**Start:** `POST /workflows/server-lifecycle/update-nodepool`, JSON
(`extra="forbid"`): `mce_cluster` (with or without `ocp4-`), `cluster` (the
day1 file's name without `.yaml`), `replicas` (≥ 0) and exactly one of
`infra_env_kind` (`replicas` is the TOTAL over the cluster's NodePools whose
InfraEnv is the kind or `<kind>-…`, spread within one replica) and
`nodepool` (that NodePool's replicas, set exactly). Both or neither: 422.
Answers `202 {"workflow_id": "update-nodepool-<cluster>", "run_id"}`; 409
while a run of the cluster runs, and while `upgrade-cluster-<cluster>` runs
(its `detail` says which).

**What it does:** reads the cluster file in day1 `main` and its NodePools on
the MCE (they must agree, both ways), plans, and through its child
(`scale-up-nodepool-<cluster>` or `scale-down-nodepool-<cluster>`) commits
only the `replicas:` lines to day1 `main`, syncs the cluster's Argo CD
Application to that commit, and checks that the NodePools show the
replicas. On a scale-down, a NodePool labelled or annotated
`redbull.io/scale-down-policy` (`fewest-pods`, `least-requested`,
`least-utilized`) has its leaving servers chosen and marked first; without
one CAPI picks at random. Freed servers stay in the MCE's inventory. Done
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
`result` (`UpdateNodePoolResult`) has the NodePools before and after and,
in `scale`, the child's commit, the NodePools read back, the servers chosen
and those seen deleting. `error` is the root failure's message only: a
child's failure reads `<child id> failed — <Type>: <message>`; the parent's
own refusals name no type.

## 2. Day1's routes

All under `/api/day1/clusters/{name}`, with the page's `?site=&mce=`. `501
FEATURE_DISABLED` on all three while `DAY1_SCALE_NODEPOOLS` is off.

**`GET .../scale`** (any signed-in user): what the Scale dialog offers, from
the cluster file on `main`, so it works without live status.

```json
{ "cluster": "ocp4-prod-lark-site1", "mce": "ocp4-prod-mce-site1-a", "flavor": "agent-sized",
  "nodepools": [ { "index": 0, "name": "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb",
                   "infra_env": "dell-r660-site1-128c-1024gb-5tb", "replicas": 3,
                   "locked_by": "agent-sized", "locked_replicas": 3, "unnamed": null } ],
  "kinds": [ { "kind": "dell-r660-site1-128c-1024gb-5tb",
               "nodepools": ["prod-lark-site1-dell-r660-site1-128c-1024gb-5tb"],
               "total": 3, "locked": ["prod-lark-site1-dell-r660-site1-128c-1024gb-5tb"] } ] }
```

- `name` is the chart's (`name`, else `<clusterName>-<infraEnvName>`, else
  `<clusterName>-<agentLabelSelector.nodeLabelValue>`), the name the
  workflow matches day1 with the MCE by; `null` with `unnamed` saying why.
- `replicas` is the file's (1 when absent, the chart's default; `null` when
  not a whole number). `locked_by`/`locked_replicas`: the cluster's flavor
  locks `nodepools[<index>].replicas`.
- `kinds`: this cluster's InfraEnvs, and the common start of sibling
  InfraEnvs (those differing only in their last dash segment); `nodepools`
  are those of this file the kind selects, `locked` those a flavor locks (the
  kind cannot be scaled).

**`POST .../scale`** (admin), `{"replicas": N, "infra_env_kind": "..."}` or
`{"replicas": N, "nodepool": "..."}`, exactly one, Kubernetes names, `N`
0-10000, no other field. Day1 adds `mce_cluster` (the file's MCE folder) and
`cluster` (the file stem). `202` with the run (`status: "running"`).
- `422 VALIDATION_ERROR`: the body; a NodePool a flavor locks, to anything
  but its locked value; a kind that selects one. Nothing is sent.
- `409 SCALE_ALREADY_RUNNING`: the orchestrator's 409, its words in
  `detail`.
- `504 AMBIGUOUS_WRITE`: sent, no answer; it may have started. Read the run
  first; never retried.
- `502 DEPENDENCY_UNAVAILABLE`: the orchestrator could not be reached or
  refused otherwise; nothing started.

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
reason}], deleting: [machine]}`. Failed, `error` is the workflow's words and
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
