# Creating a cluster through the provision-cluster workflow (2026-11-12)

The platform now has a Temporal workflow that creates a hosted cluster:
`provision-cluster`, started through the workflows orchestrator. Wingman
can start it instead of opening its own merge request (ADR-0042). This note
is the contract between day1 and the web for that mode, written before the
code. Wingman only starts the run and shows it: the procedure, its checks
and its phases are the workflow's (ADR-0038's rule).

## 1. What the workflow takes and does

- **Start:** `POST /workflows/cluster-lifecycle/provision-cluster?cluster=<name>&mce=<folder>`,
  with the cluster file itself as the body (`Content-Type: application/yaml`).
  It answers `202 {"workflow_id", "run_id"}` at once.
  - `cluster` is the cluster's name with or without `ocp4-`; the workflow
    writes the file `ocp4-<name>.yaml`. It must be a lowercase DNS-1123
    label of at most 24 characters.
  - `mce` is the MCE folder name, as under `sites/<site>/mces/`; the
    workflow finds the site from it.
  - The body is sent verbatim, comments included. It must hold `owner`,
    `mastertag` and a nodepool, and must not hold `vlanId`, `dhcp_values`,
    `mcConfigMap` or `AutomateAllocation`.
- **What it does:** it reads day1 main, finds the MCE folder, and judges the
  file against the value layers. Then it reserves a segment (the
  allocate-segment workflow, as a child), pushes the file with the
  allocation added on its own branch, opens the merge request, and waits,
  with no deadline, for a person to merge it. After the merge it registers
  the cluster in the day2 sig repos the value layers list.
- **The run:** its id is `provision-cluster-<file stem>`
  (`provision-cluster-ocp4-prod-rcs-site1-a`). `GET /workflows/runs/{id}`
  gives `status` (`RUNNING`, `COMPLETED`, `FAILED`, `TERMINATED`, ...),
  `progress` (its `phase`, and once there is one, `merge_request_url` and
  `merge_request_state`), `result` once completed, and `error` once failed.
- **Refusals:**
  - `409`: a run for this cluster is already going.
  - `422`: the name or the body's shape is unusable.
  - Everything else (an unknown MCE folder, a cluster already on main, a
    file the chart would not render, a closed merge request, ...) is a
    FAILED run whose `error` names the reason, never a 4xx at the start.
  - Re-running a cluster after a failure converges: the same segment, the
    same branch, and the same merge request found again.

## 2. What Wingman sends

The create form is unchanged. Wingman still renders the file from the
template, the flavor and the inputs, and checks it exactly as today
(naming, flavor locks, machine configs, the nodepool ratio, the MCE). The
only change is the last step: instead of a commit and a merge request,
day1 starts the workflow with:

| Workflow input | From |
|---|---|
| `cluster` | The new file's stem without `ocp4-` (`prod-rcs-site1-a`) |
| `mce` | The MCE the person chose (its folder name) |
| body | The rendered file, with Wingman's provenance comment header |

The flavor, its version and the requested add-ons travel in that comment
header, as they do in today's merge requests; the workflow keeps comments.
Day1 logs who started the run: the orchestrator has no auth and no
"requested by" field.

Modify, delete, sync and import still open Wingman merge requests: the
workflow only creates.

## 3. The API (day1)

The setting `DAY1_PROVISIONER` chooses the mode: `merge-request` (the
default, today's flow) or `workflow`. `workflow` needs `WORKFLOWS_API_URL`
(day1 refuses to start without it). `DAY1_FAKE_FLEET` fakes the
orchestrator for a local demo.

### `POST /api/day1/clusters` (create)

- `merge-request`: unchanged, `201` with the merge request (`MRDetail`).
- `workflow`: `202` with the run:

```json
{
  "workflow_id": "provision-cluster-ocp4-prod-rcs-site1-a",
  "cluster": "ocp4-prod-rcs-site1-a",
  "status": "running",
  "phase": null,
  "error": null,
  "merge_request_url": null,
  "merge_request_state": null
}
```

  Errors, besides the form's own `422`s:

  | Status | Code | When |
  |---|---|---|
  | 409 | `ALREADY_EXISTS` | A provision run for this cluster is already going |
  | 422 | `VALIDATION_ERROR` | The orchestrator refused the name or the file (its own words in `problems`) |
  | 502 | `DEPENDENCY_UNAVAILABLE` | The orchestrator could not be reached: nothing started |
  | 504 | `AMBIGUOUS_WRITE` | Sent, but no answer: the run may exist. Look at it before trying again |

### `GET /api/day1/clusters/{name}/provision-run`

The newest provision run for the file stem `name`, in the same shape as
above. `status` is lowercase; `phase` is the workflow's own string, never
a list Wingman keeps. `merge_request_url` appears once the workflow has
opened the merge request. Any signed-in user may read it.

- `404 NOT_FOUND`: the orchestrator has no run for this cluster.
- `501 FEATURE_DISABLED`: the mode is `merge-request`.
- `502 DEPENDENCY_UNAVAILABLE`: the orchestrator did not answer.

### `GET /api/day1/clusters/provisioner`

`{"mode": "merge-request" | "workflow"}`, so the form can say what Create
will do before it is pressed.

## 4. The web

- The create form's Review says what Create does: "Opens a merge request"
  or "Starts the provision-cluster workflow".
- After Create, in `workflow` mode, the page stays on the result and shows
  the run, read again every 10 s while it runs, the same way a node's
  uninstall run is shown:
  - its status;
  - its phase, the workflow's word humanized (`awaiting-merge` becomes
    "Awaiting merge");
  - a link to the merge request once there is one;
  - the error, in the workflow's words, when it failed.
- In `merge-request` mode nothing changes: the toast and the approval page.

## 5. Open questions for the team

1. **The 24-character limit.** Wingman's own rule is the 63-character
   DNS label of the HostedCluster and its namespace, and a name it suggests
   can pass 24 (`prod-agent-standar-site1-a` is 26). Is 24 counted on the
   name without `ocp4-`, and should Wingman's suggestion and checks follow
   it in `workflow` mode? Until then, the workflow's 422 is shown as is.
2. **The merge request is the workflow's, not Wingman's.** Its title and
   branch don't follow Wingman's MR conventions (ADR-0007), so Wingman's
   approvals page, the cluster list's pending rows, the name suggestion's
   "taken" set and the "already being created" check don't see it. Should
   the workflow's MR carry Wingman's labels or title, or should Wingman list
   provision runs (`GET /workflows/runs?workflow_type=ProvisionClusterWorkflow`)
   alongside its MRs?

   **Answered (2026-11-13, ADR-0042's amendment): neither; Wingman finds it
   by its branch.** The workflow's source branch is always
   `provision-cluster/<file stem>` (its `provision_cluster_branch`), and
   nothing changes on the workflow's side. In either mode, day1 counts each
   open MR on that branch as an open create: a taken name for the
   suggestion, a refused create (`409 ALREADY_EXISTS` with the MR's URL),
   and a cluster on its MCE for placement. `GET /api/day1/approvals` lists
   it with `"opened_by_workflow": "provision-cluster"` (`null` on Wingman's
   own MRs). It is reviewed and
   merged there: the workflow records no requester, so Wingman's "nobody
   approves their own change" can't hold, and approving, rejecting or
   editing it through Wingman answers `404`.
3. **Add-ons.** The workflow registers the cluster in the day2 sigs its
   value layers list. The flavor's add-ons are recorded in the header, as
   today, and still installed by day2 afterwards. Is that the intended
   split?
4. **The run's class name.** `ProvisionClusterWorkflow` is what the
   orchestrator's run list shows today. Wingman reads runs by id, so it
   doesn't depend on it.
5. **Who started a run.** The orchestrator records no user. Is a
   `requested_by` input planned?
