# Upgrading a cluster through the upgrade-cluster workflow (2026-11-13)

The platform has a Temporal workflow that upgrades one hosted cluster:
`upgrade-cluster`, started through the workflows orchestrator (its own page is
`<orchestrator>/ui/cluster-upgrade`). Wingman starts it from the cluster page,
shows its run there, and sends the decisions a person makes on it
(ADR-0055). This note is the contract between day1 and the web, written
before the code. Wingman only starts a run, shows it and passes decisions on:
the procedure, its checks, its phase list and which decision it accepts when
are the workflow's (the rule of ADR-0038 and ADR-0042).

Sources: `team-redbull/workflows` on GitHub (`workflow_domains/cluster_upgrade/router.py`,
`shared/models/cluster_upgrade.py`, `workflow_domains/routers/runs.py`, the
orchestrator page `workflow_domains/cluster_upgrade/ui/index.html`) and the
orchestrator's `/openapi.json`, read by GET only.

## 1. What the workflow takes and does

**What it does.** It takes one hosted cluster from the release it runs to a
target, **only through commits to the cluster's day1 file plus a sync of that
cluster's Argo CD Application on its MCE**. It never patches the
HostedCluster or a NodePool. It plans the path along the day1 repo's
`upgrade/ladder.yaml` (the control plane through every minor, never skipping
a `must` rung, workers never more than `maxWorkerSkew` minors behind), pins
every release to a digest, runs a pre-flight, and waits for one approval
before anything is committed. Then it walks the plan:
- a control-plane step: admin acks if a minor needs them, a per-MCE slot,
  commit, sync, watch;
- a `confirm-day2` wait after every control-plane step;
- then one NodePool at a time: a `continue` from a person before each (in
  manual mode), commit, sync, watch the roll, a gate and a soak.

An upgrade agent (an LLM service) is asked only when a gate fails or a watch
stalls; it proposes, a person decides. The workflow's docs page says "Built,
and run on a sandbox HostedCluster — not in production yet".

**Start:** `POST /workflows/cluster-upgrade/upgrade-cluster`, JSON
(`extra="forbid"`):

| Field | Default | Meaning |
|---|---|---|
| `cluster` | required | The day1 cluster **file's name** without `.yaml` (also its Application's name). Not the HostedCluster's name. The run finds the site and MCE from the file's folder; sending `mce_cluster` is a 422. |
| `target_version` / `target_minor` | exactly one | A release `X.Y.Z` (or `-x86_64`) that must be in the mirror; or a minor `4.21`, for which the run picks the newest release that is mirrored and a ladder rung. |
| `nodepool_order` | the file's `upgrade.nodePoolOrder`, else by zone, else file order | The order NodePools roll in, each once. |
| `max_unavailable` | none | `{"<nodepool>": 2 \| "33%"}`, written into `nodepool[].inPlace.maxUnavailable` with that NodePool's commit, and kept there. |
| `nodepool_mode` | `manual` | `auto` rolls each NodePool after the previous soak without a `continue`. Only for a file with `upgrade.wave` 0 or 1, else planning fails. |
| `workers_to_target` | `true` | `false`: control plane only; NodePools move only where the path forces it. |
| `auto_approve` | `false` | The run approves its own plan. Only `upgrade.wave` 0 or 1. |
| `requested_by` | required | Who asked; recorded in the run's log, trusted as sent. |

It answers `202 {"workflow_id", "run_id"}` at once. **Starting is the dry
run:** the run plans, pins and pre-flights, then waits for `approve` with
nothing committed; an `abort` there ends it CANCELLED.

**The run id** is `upgrade-cluster-<file stem>`
(`upgrade-cluster-ocp4-prod-lark-site1`). One run per cluster at a time. A
closed run's id is reused by the next upgrade, so `GET /workflows/runs/{id}`
always describes the newest. The run continues-as-new after every step.

**`GET /workflows/runs/{id}`** gives `status` (Temporal's: `RUNNING`,
`COMPLETED`, `FAILED`, ...), `error` (the root cause) and `progress`, while
it runs and after a failure:
- `phase`: the workflow's own word (`planning`, `preflight`,
  `awaiting-approval`, `waiting-for-slot`, `admin-acks`, `awaiting-admin-ack`,
  `control-plane-step`, `awaiting-day2-confirm`, `awaiting-continue`,
  `nodepool-roll`, `nodepool-gate`, `agent-invocation`, `needs-human`,
  `paused`, `postflight`, `aborting`, `done`, `cancelled`, `aborted` today).
  The list moves; Wingman keeps none of it.
- `waiting_for`: what has to happen next, in words, or `null`. It names the
  decision first when a person is needed (`"approve: 4.16.27 → 4.21.40 in 9
  steps (...)"`, `"continue, once the customer's readiness checks after ...
  pass: ..."`, `"retry or abort: <reason>"`), and describes machine waits
  too (`"a control-plane slot on <mce>: ..."`). A non-null `waiting_for` does
  not always mean a person.
- `mce_cluster`, `plan` (`control_plane`, `target`, `max_worker_skew`,
  `nodepools{name: version}`, `steps[{kind control-plane|workers, version,
  reason ladder|target|skew|rung-required|final, nodepools[]}]`, `pinned`),
  `profile` (`generic`|`zoned`), `current_step`, `current_nodepool`,
  `nodepools_done[]`, `control_plane_version`, `nodepool_versions{}`,
  `max_unavailable{}`, `paused`, `pending_actions[{action{action_id, kind,
  target, args, rationale}, decision pending|approved|rejected, decided_by,
  executed, result}]`, `last_verdict{diagnosis, confidence, verdict, ...}`,
  `verified_against_graph`, `log[{at, event, by, detail}]` (the last 20).

Completed, `result` is `{outcome done|cancelled|aborted, mce_cluster,
cluster, plan, steps_completed, control_plane_version, nodepool_versions,
log}`. A run that fails at planning lists every failed check in `error`.

**Decisions** are Temporal Updates, judged by the run's own validators:
`POST /workflows/cluster-upgrade/upgrade-cluster/{workflow_id}/<decision>`.

| Decision | Body (`extra="forbid"`) | Accepted while |
|---|---|---|
| `approve` | `{by, reason?}` | `awaiting-approval` |
| `approve-admin-ack` | `{by, reason}` (reason required) | `awaiting-admin-ack` |
| `continue` | `{by, nodepool?}` (no `reason`) | `awaiting-continue` (the customer's sign-off after their own readiness checks) |
| `confirm-day2` | `{by, reason?}` | `awaiting-day2-confirm` (the day2 team synced their layer) |
| `pause` / `resume` | `{by, reason?}` | after approval / while paused |
| `abort` | `{by, reason}` (reason required) | any open phase, once. Before approval: CANCELLED. After: commits `pausedUntil` and syncs: ABORTED. Nothing is rolled back. |
| `retry` | `{by, reason?}` | `needs-human`, `awaiting-admin-ack` |
| `actions/{action_id}/approve` / `reject` | `{by}` | `needs-human`, the agent's proposal pending |

Answers: `200 {workflow_id, decision}`; **409** the run was not waiting for
that (the detail is the run's own reason and names what it waits for); 404
no such running run; 504 no answer in 15 s (no brain worker; the Update may
have landed); 500 the Update failed otherwise.

**Targets:** `GET /workflows/cluster-upgrade/upgrade-targets?cluster=<file stem>`,
the only synchronous route. It runs a short read-only
`upgrade-targets-<cluster>` run (two day1 reads at `main`) and waits up to
60 s. 200: `{cluster, mce_cluster, mce_version, control_plane_version (the
file's mastertag), supported_minors[], ladder_revision,
verified_against_graph, targets[{version, minor, steps, control_plane_steps,
newest_in_minor, must}], nodepools[{name, workertag, upgrade_type, zone,
replicas, max_unavailable}], nodepool_order[]}`. Targets are ladder rungs
newer than the mastertag, of a minor the MCE supports, that a path reaches,
newest first. **An empty list is an answer**, not an error, and does not say
why (already at the newest, no mastertag, a NodePool ahead of the control
plane, ...): a run started toward the expected target fails its planning
naming the rule. 404: day1 has no such file. 409: the file or the rules
cannot be used (the detail says why). 504: no limb answered.

**Refusals at the start:** 409 (the cluster already has a run) and 422 (the
body). Everything else is a FAILED run at planning, with every failed check
listed, or a `needs-human` wait after approval.

**What it changes in Git, and where.** It pushes straight to day1 **`main`**
(no branch, no merge request), as `cluster-upgrade-workflow`, one file per
commit, message `upgrade(<cluster>): <summary> [upgrade-cluster-<cluster>]`,
after running day1's own validator. Every commit is compare-and-set on the
file's blob: a file someone else changed since the run last read or wrote it
is never committed over; the run stops and asks a person. The lines it edits:
- `mastertag: <v>-x86_64` for a control-plane step, with every NodePool's
  `workertag` pinned explicitly so no worker moves with it;
- `nodepool[<name>].workertag` (and `inPlace.maxUnavailable` when the
  request set one) for a NodePool step;
- post-flight drops a top-level `workertag` it added; the per-NodePool
  `workertag` lines stay (equal to `mastertag`);
- `pausedUntil: "true"` on an abort after approval. **Nothing in the
  workflow ever removes it**: a person has to.

It also gives admin acks inside the hosted cluster, syncs the Application on
the MCE (refused when anything but its own change is out of sync), never
syncs day2, and writes incident pages to the team's Brain repo when the
agent is called.

**What it needs from the caller:** the file stem, a target from
`upgrade-targets`, `requested_by`, and the optional fields. No MCE, no site,
no credentials: the orchestrator has no auth.

## 2. What the orchestrator's own page does

`<orchestrator>/ui/cluster-upgrade` is one self-contained page with no auth,
polling every 10 s; it calls itself temporary "until the ClickCluster
Platform UI exists". Wingman is that UI for one cluster at a time.
- A runs list (every `UpgradeClusterWorkflow` run), and for one run: its
  facts (MCE, path, profile, control-plane version, maxUnavailable, the
  ladder's checked date, the run id), a "Waiting for" box with `waiting_for`
  verbatim and the phase's buttons, Pause/Resume and Abort while open, the
  plan as a track of steps, the agent's last verdict and its proposals, the
  log (newest first).
- Decision dialogs: who decides, a reason (required for abort and
  approve-admin-ack), the next NodePool for continue. A 409's detail is
  shown verbatim.
- A "New upgrade" form: the cluster, a target from `upgrade-targets` with
  each target's step counts, the NodePools in roll order with a
  maxUnavailable each (sent only when changed), "Who starts each NodePool"
  (manual / auto, lab and canary only), "Approve automatically".

Two of its choices copy workflow knowledge: a `PHASES` map (phase → words)
and a `DECISIONS` map (phase → buttons), which the page itself calls "the
page only offers; router.py validates again". Wingman keeps no phase list,
and one small decisions map until the run says which decisions it accepts
(§5, question 4).

## 3. The day1 API

Behind `DAY1_UPGRADES` (default `false`). It needs `WORKFLOWS_API_URL`, and
day1 refuses to start without it (ADR-0009). `WORKFLOWS_TARGETS_TIMEOUT_SECONDS`
(default 65) is the targets read's own timeout: the orchestrator waits up to
60 s. Off: every route below answers `501 FEATURE_DISABLED`, and the web
shows nothing. `DAY1_FAKE_FLEET` fakes the workflow for a local demo.

Every route is under `/api/day1/clusters/{name}`, with the optional
`?site=&mce=` of the other cluster routes. `{name}` is the cluster file's
stem, which is the workflow's `cluster`; the run's id is
`upgrade-cluster-<name>`. A cluster the day1 repo does not have is
`404 NOT_FOUND` everywhere. Every start and decision is `AdminUser`; day1
fills `requested_by` and `by` from the signed-in user (never from the body)
and logs who did what (`upgrade_started`, `upgrade_decided`). Reading the
run is `CurrentUser`. Nothing is retried (ADR-0006).

### `GET .../upgrade-targets` (admins)

The orchestrator's targets, passed through. Admins only: only admins start
upgrades, and each call starts a short Temporal run.

```json
{
  "cluster": "ocp4-prod-lark-site1",
  "mce": "ocp4-prod-mce-site1-a",
  "mce_version": "2.8.2",
  "control_plane_version": "4.18.22",
  "supported_minors": ["4.18", "4.17", "4.16"],
  "ladder_revision": "3f2a9c1",
  "verified_against_graph": "2026-10-31",
  "targets": [
    {"version": "4.18.56", "minor": "4.18", "steps": 2, "control_plane_steps": 1, "newest_in_minor": true, "must": true}
  ],
  "nodepools": [
    {"name": "prod-lark-site1-dell-r660-site1-128c-1024gb-5tb", "workertag": null, "upgrade_type": "InPlace",
     "zone": null, "replicas": 3, "max_unavailable": null}
  ],
  "nodepool_order": ["prod-lark-site1-dell-r660-site1-128c-1024gb-5tb"]
}
```

An empty `targets` is an answer: nothing newer to offer, and the workflow
doesn't say why.

| Status | Code | When |
|---|---|---|
| 404 | `NOT_FOUND` | The workflow's day1 has no such file (it reads its own copy of the repo: §5, question 6) |
| 409 | `UPGRADE_TARGETS_REFUSED` | The file or the rules cannot be used; `detail` is the workflow's words |
| 502 | `DEPENDENCY_UNAVAILABLE` | The orchestrator was not reached, did not answer in `WORKFLOWS_TARGETS_TIMEOUT_SECONDS`, or answered its 504 (no limb answered) |

### `POST .../upgrade` (admins)

```json
{
  "target_version": "4.18.56",
  "target_minor": null,
  "nodepool_order": ["pool-a", "pool-b"],
  "max_unavailable": {"pool-a": 2, "pool-b": "33%"},
  "workers_to_target": true,
  "nodepool_mode": "manual",
  "auto_approve": false
}
```

Exactly one of `target_version` and `target_minor`; every other field may be
left out, and only what is sent reaches the workflow. Unknown fields are
refused. Day1 adds `cluster` (the stem) and `requested_by` (the signed-in
user), and logs `upgrade_started`. `202` with the run, as below, with only
`workflow_id`, `cluster` and `status: "running"` known yet.

| Status | Code | When |
|---|---|---|
| 409 | `UPGRADE_ALREADY_RUNNING` | The cluster already has an open upgrade run |
| 422 | `VALIDATION_ERROR` | The body (day1's, or the orchestrator's 422, its findings in `problems`) |
| 502 | `DEPENDENCY_UNAVAILABLE` | The orchestrator could not be reached, or refused otherwise: nothing started |
| 504 | `AMBIGUOUS_WRITE` | Sent, no answer: the run may exist. Read the run before starting again |

### `GET .../upgrade-run` (any signed-in user)

The run read by its id, in Wingman's shape. Phases, reasons and texts are
the workflow's, passed through.

```json
{
  "workflow_id": "upgrade-cluster-ocp4-prod-lark-site1",
  "cluster": "ocp4-prod-lark-site1",
  "status": "running",
  "phase": "awaiting-approval",
  "waiting_for": "approve: 4.18.22 → 4.18.56 in 2 steps (control plane, then 2 NodePools)",
  "mce": "ocp4-prod-mce-site1-a",
  "plan": {
    "control_plane": "4.18.22",
    "target": "4.18.56",
    "max_worker_skew": 2,
    "nodepools": {"pool-a": "4.18.22", "pool-b": "4.18.22"},
    "steps": [
      {"kind": "control-plane", "version": "4.18.56", "reason": "target", "nodepools": []},
      {"kind": "workers", "version": "4.18.56", "reason": "final", "nodepools": ["pool-a", "pool-b"]}
    ]
  },
  "profile": "generic",
  "current_step": 0,
  "current_nodepool": null,
  "nodepools_done": [],
  "control_plane_version": "4.18.22",
  "nodepool_versions": {"pool-a": "4.18.22", "pool-b": "4.18.22"},
  "max_unavailable": {},
  "paused": false,
  "pending_actions": [],
  "last_verdict": null,
  "verified_against_graph": "2026-10-31",
  "log": [{"at": "2026-11-13T10:00:00Z", "event": "planned", "by": "alice", "detail": "2 steps"}],
  "outcome": null,
  "steps_completed": null,
  "error": null,
  "decisions": null
}
```

- `status` is lowercase. While it is `running`, the run is open.
- `pending_actions[]` is each agent proposal flattened: `{action_id, kind,
  target, args, rationale, decision, decided_by, executed, result}`.
- `last_verdict` is `{diagnosis, confidence, verdict}` or `null`.
- `log` is in the workflow's order (oldest first); the web shows it newest first.
- Once completed: `outcome` (`done`, `cancelled`, `aborted`), `steps_completed`,
  and the final versions; `phase` and `waiting_for` are `null`.
- `decisions` is `progress.decisions` when the run carries it (§5, question
  4): the decisions it accepts now. `null` until then.

| Status | Code | When |
|---|---|---|
| 404 | `NOT_FOUND` | No upgrade run for this cluster yet |
| 502 | `DEPENDENCY_UNAVAILABLE` | The orchestrator did not answer: the run is unknown, not "none" |

### `POST .../upgrade-run/{decision}` (admins)

`decision` is one of `approve`, `approve-admin-ack`, `continue`,
`confirm-day2`, `pause`, `resume`, `abort`, `retry`. Body
`{"reason"?: "...", "nodepool"?: "..."}`:
- `reason` is required for `abort` and `approve-admin-ack` (the workflow
  requires one), optional otherwise, and not taken by `continue`;
- `nodepool` is for `continue` only (which NodePool rolls next; default: the
  next in the run's order).

Day1 sets `by` and logs `upgrade_decided`. `200`:

```json
{"workflow_id": "upgrade-cluster-ocp4-prod-lark-site1", "decision": "approve", "run": { "...": "the run, read again" }}
```

`run` is `null` when the run could not be read again: the decision was
taken all the same.

### `POST .../upgrade-run/actions/{action_id}/approve` and `.../reject` (admins)

An agent proposal; no body. Day1 sets `by`. `200` as above, with `decision`
`approve-action` or `reject-action`.

Errors of both decision routes:

| Status | Code | When |
|---|---|---|
| 404 | `NOT_FOUND` | No running upgrade run for this cluster |
| 409 | `UPGRADE_DECISION_REFUSED` | The run was not waiting for that; `detail` is the run's own words, naming what it waits for |
| 422 | `VALIDATION_ERROR` | A missing reason, a `nodepool` on another decision, an unknown decision |
| 502 | `DEPENDENCY_UNAVAILABLE` | Not sent, or the orchestrator's 500 (the Update failed) |
| 504 | `AMBIGUOUS_WRITE` | Sent, no answer, or the orchestrator's 504 (15 s; the Update may have landed): read the run before deciding again |

### Versions belong to the workflow while `DAY1_UPGRADES` is on

A modify (`PATCH /clusters/{name}`) or an MR review edit
(`PUT /approvals/{iid}`) that changes `mastertag` or any `workertag`
(top-level, or a NodePool's), or adds or changes `pausedUntil`, is refused
with `422 VALIDATION_ERROR`, one line in `problems` per key, each ending
"Versions change through Upgrade on the cluster page". Removing
`pausedUntil` is allowed: after an aborted upgrade a person clears it. A new
NodePool may carry a `workertag` only equal to the version it would follow
without one. Create still writes the starting `mastertag` (ADR-0034), and a
review edit of a create MR may still change it: the cluster does not exist
yet. With the setting off, nothing changes (ADR-0055, amending ADR-0012).

### Metrics

New `workflows` operations (`docs/ops/metrics.md`): `upgrade_targets`,
`start_upgrade`, `decide_upgrade` (every decision and proposal; no decision
name and no cluster in the labels). The run read is `get_run`.

## 4. The web (the cluster page; no new page)

- **Overview, the Mastertag row:** an "Upgrade" button for admins, when
  upgrades are on and the cluster has no open run. It opens a dialog fed by
  `upgrade-targets`, with a clear loading state (the read can take up to a
  minute):
  - the targets (version, minor, control-plane steps and steps in all,
    newest of its minor), the ladder's checked date and the MCE's supported
    minors;
  - the NodePools in their default roll order with up/down and a
    maxUnavailable each (sent only when changed), and "Control plane only"
    (`workers_to_target: false`);
  - `nodepool_mode: auto` and `auto_approve` under a "Lab and canary
    clusters" disclosure; Wingman doesn't check the wave, the run's planning
    does;
  - the dialog says what Start does: it plans and checks, then waits for
    approval, with nothing committed before approval;
  - an empty list says there is nothing newer to offer.
- **Overview, an Upgrade panel** while the cluster has a run (its outcome
  stays once it closes):
  - the status and the phase, humanized from the workflow's word, and
    `waiting_for` verbatim;
  - the decision buttons (below), each confirmed in a small dialog (a reason
    field; required for Abort and Approve admin ack; the NodePool for
    Continue);
  - the plan as a step list, each step done, current or pending from
    `current_step`, `nodepools_done` and `current_nodepool`; the current
    NodePool links to the Nodes tab, which already shows its in-place
    progress (ADR-0038);
  - the agent's last verdict and its pending proposals with Approve/Reject;
  - the log (newest first), the error, the run id and the MCE.
  - A refused decision's 409 is shown in the workflow's own words.
  - Read again every 10 s while the run is open.
- **Which decision buttons:** `decisions` when the run carries it. Until
  then one small map, phase → decisions, the orchestrator page's own:
  `awaiting-approval` → approve; `awaiting-day2-confirm` → confirm-day2;
  `awaiting-admin-ack` → approve-admin-ack, retry; `awaiting-continue` →
  continue; `needs-human` → retry, plus the pending proposals. Pause (Resume
  when paused) and Abort while the run is open. A phase the map doesn't know
  shows `waiting_for` and only Pause/Abort, never a guess. The run's
  validators judge every decision.
- **History tab:** nothing to build. The workflow's commits to the file
  appear there (`upgrade(<cluster>): ... [upgrade-cluster-<cluster>]`).
- Not in this version: a clusters-list badge, a list of runs waiting for a
  person on the approvals page.

## 5. Open questions for the team

1. **Production readiness.** The limbs are installed by hand on the sandbox
   and "not in production yet". When will they be deployed by Argo CD, and
   should `DAY1_UPGRADES` stay off everywhere until then?
2. **Direct pushes to day1 `main`.** The upgrade commits to `main` without a
   merge request. In the air-gapped GitLab, is `main` protected so that its
   token may push? Is a reviewed MR wanted instead, or is `approve` the
   review?
3. **Who may decide.** `continue` is "the customer's sign-off" and
   `confirm-day2` the day2 team's. Wingman has admins and viewers. Should
   the cluster's owner team be allowed `continue`, and the day2 team
   `confirm-day2`, or all admins only (this version)?
4. **`progress.decisions`.** Will the team add the list of decisions the
   run accepts now? Wingman's map, and the orchestrator page's, could then
   go.
5. **Who clears `pausedUntil` after an aborted upgrade,** and when? Nothing
   in the workflow does. Is a person's day1 edit the intended way?
6. **One day1 repo.** The workflow reads and writes the day1 repo its limb
   is configured with. A Wingman deployed against a copy (a test GitLab)
   gets 404s from `upgrade-targets`, or upgrades the clusters of the
   original. Is a per-deployment day1 repo for the limb planned?
7. **`upgrade.wave` and the `upgrade:` block.** Wingman's template writes
   none, so every Wingman cluster is "production" to the upgrade (manual
   approve and continue, no auto). Should a flavor be able to set
   `upgrade.wave` or `upgrade.nodePoolOrder`?
8. **One run id per cluster.** A cluster's past upgrades are visible only
   through the run list's closed rows under one id, and the History tab's
   commits. Is showing only the newest run enough?
9. **Merging during an upgrade.** A Wingman MR merged mid-upgrade (a modify,
   a flavor sync, a rollout's MR, a delete) stops the run at `needs-human`
   until someone retries (its compare-and-set and its sync refuse). Should
   the flavor rollout skip clusters with an open upgrade, and should the
   edit dialogs warn?
10. **The targets read starts a Temporal run.** Every opening of the Upgrade
    dialog starts an `upgrade-targets-<cluster>` run (shared when
    concurrent). Is that load fine, or should Wingman keep the answer for a
    minute?
