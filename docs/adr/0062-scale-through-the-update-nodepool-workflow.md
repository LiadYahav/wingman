# ADR-0062: A hosted cluster's NodePools are scaled through the update-nodepool workflow, behind a setting, and while it is on their replicas change only that way

Date: 2026-11-16
Status: Accepted; amends ADR-0012 (who owns each NodePool's `replicas`), ADR-0037 and ADR-0044 (a sync's and a rollout's MR leave them out); amended 2026-11-16 (no Scale dialog: each NodePool scales on its card, a hardware type's total in a small dialog; then every scale confirmed first, with the scale-down policy)

## Context

How many workers a hosted cluster runs is each `nodepool[]` entry's
`replicas` in its day1 file. Today a person changes it by editing the file
(the cluster page's YAML editor, an edit of a pending merge request), and a
flavor that locks `nodepools[<i>].replicas` (ADR-0026) sets it back through
a sync or a rollout's merge request (ADR-0037, ADR-0044). Nothing chooses
which servers leave on a scale-down: CAPI picks at random.

The platform team wrote the `update-nodepool` workflow (team-redbull/workflows,
branch `feat/update-nodepool`, designed with the operator 2026-11-03 and
2026-11-08; not merged yet). `POST /workflows/server-lifecycle/update-nodepool`
takes `{mce_cluster, cluster, replicas}` and exactly one of `infra_env_kind`
(a total spread over the cluster's NodePools of that InfraEnv kind, within
one replica of each other) and `nodepool` (that one, set exactly). The run
(`update-nodepool-<cluster>`, one per cluster, refused while an
upgrade-cluster run of the cluster runs) reads the NodePools in day1 and on
the MCE and refuses any disagreement, plans, and through its child
(`scale-up-nodepool-<cluster>` or `scale-down-nodepool-<cluster>`) commits
only the `replicas:` lines to day1 `main`, syncs the cluster's Argo CD
Application itself and checks that the NodePools show the new replicas. On a
scale-down a NodePool's `redbull.io/scale-down-policy` (`fewest-pods`,
`least-requested`, `least-utilized`) chooses and marks the servers that
leave; without one, CAPI picks. Its operator's rule: **NodePool replicas
change only through update-nodepool.**

## Decision

1. **`DAY1_SCALE_NODEPOOLS`** (default `false`) turns it on; it needs
   `WORKFLOWS_API_URL` (or `DAY1_FAKE_FLEET` in development) and day1
   refuses to start without it (ADR-0009). The chart sets it from
   `day1.scaleNodepools.enabled` (in `values.schema.json`; the chart refuses
   it without `workflows.url`). Off, the routes answer `501
   FEATURE_DISABLED` and nothing else changes.
2. **Scale lives on the cluster page's Nodes tab**, where the NodePools are
   (no new page). A "NodePool sizes" panel lists the cluster file's
   NodePools on `main` (not the MCE's, so it works with live status off),
   an admin's **Scale** opens a dialog with the API's two ways, and the run
   shows in place for anyone signed in:
   - **By hardware kind**: a new total for the NodePools of one InfraEnv
     kind; the dialog shows which of this cluster's NodePools the kind
     selects and their total now. The kinds offered are this cluster's own
     InfraEnvs and the common start of sibling InfraEnvs (two or more that
     differ only in their last dash segment, `<k>-zone-a`/`<k>-zone-b` →
     `<k>-zone`), never shorter: a shorter kind would also take other
     hardware (`domain.scale.kind_choices`). Which NodePools a kind selects
     is the workflow's rule (`K` or `K-…`), kept in day1 only to show them
     and to refuse a locked one; the run's result lists what it selected.
   - **One NodePool**: its exact replicas. A NodePool is named from the
     file by the chart's rule (`name`, else `<clusterName>-<InfraEnv>`),
     the rule the workflow matches day1 with the MCE by, so it needs no
     live status; an entry the file cannot name is not offered, with the
     reason, never a guessed name.
   - A confirmation in words: one commit to day1 `main` (no merge request),
     the workflow syncs Argo CD itself and checks the NodePools; on a
     scale-down the servers that leave are the NodePool's policy's, else
     CAPI's at random, and they stay in the MCE's inventory as free Agents;
     done means the NodePools show the replicas, not that nodes are Ready.
   - The run: its status, its phase and its child's (read by the child's id
     while it runs), humanized with no phase list; at the end the NodePools
     before and after, the totals, the servers chosen with policy and
     reason, those seen deleting and the commit; a failure in the
     workflow's words, with its type when the words name one.
   - Scale waits, with the reason, while a scale run or an upgrade run
     (ADR-0055) of the cluster is open: one run per cluster, never queued in
     Wingman.
3. **Wingman keeps no copy of the workflow's procedure.** No spread plan, no
   balance check, no drift check between day1 and the MCE, no list of
   phases: the run's result shows the plan and its refusal the reason
   (`NodePoolsUnbalancedError`, `NodePoolReplicasDriftError`, …). Day1
   checks only what is its own: the cluster is in the day1 repo, the body
   is well-formed (exactly one target, Kubernetes names, replicas ≥ 0), and
   the flavor's locks (4).
4. **A flavor's locked replicas are the flavor's** (the user, 2026-11-16).
   With scaling on, a NodePool whose replicas the cluster's flavor locks
   cannot be scaled ("locked by flavor X"), and a kind that selects one
   cannot either; day1 refuses both with a 422. The one move allowed is
   back to the locked value: a **Restore with update-nodepool**, a by-name
   run to it.
5. **While scaling is on, an existing NodePool's replicas change only
   through update-nodepool** (the user, 2026-11-16; amends ADR-0012). Every
   write of an existing cluster file is checked in one place,
   `cluster_file.edit_problems` (a modify, a review edit of a pending
   merge request, a flavor's sync and a rollout's MR all pass it), with one
   rule, `replicas_ownership.replicas_changes`: each NodePool on `main`
   whose `replicas` the write changes.
   - A person's YAML (the raw editor, a review edit) that changes one is
     refused with a problem pointing to Scale. A review edit is compared
     with the file on the target branch, not with the MR's branch.
   - A change Wingman writes (amends ADR-0037 and ADR-0044): a flavor's
     sync, and a rollout's per-cluster MR, leave drifted locked replicas out
     of the MR and carry the rest. The preview, the sync's answer and the
     rollout's items list each NodePool in `held_replicas`, with its
     replicas and the flavor's; the MR description says which NodePools are
     restored through update-nodepool. The sync dialog offers **Restore
     with update-nodepool** for each (one run per cluster: enable one at a
     time); the rollout panel links each cluster to its Nodes tab, which
     offers it too.
   - Left alone: a new cluster (create, by Wingman's merge request or
     provision-cluster, still sets the first replicas), a `nodepool[]` entry
     not on `main` yet, with its first replicas, and removing an entry.
   - With the setting off, nothing of this applies.
6. **A port, an adapter and a fake (ADR-0001).** `ScaleWorkflow`
   (`ports/scale.py`); `HttpScaleWorkflow` beside the other orchestrator
   adapters, sharing their client rules, its JSON read leniently
   (`scale_payloads.py`: unknown fields ignored, the branch can still
   change); `FakeScaleWorkflow` for `DAY1_FAKE_FLEET`, whose runs walk
   sample phases and plan a sample spread from the day1 files (a demo, not
   the workflow's rule).
7. **Writes are never retried (ADR-0006).** A start sent and not answered,
   or a gateway's 504, is `504 AMBIGUOUS_WRITE`: read the run first. The
   orchestrator's 409 is `409 SCALE_ALREADY_RUNNING` (new problem code,
   append-only, ADR-0004) in its words: a run of the cluster, or an
   upgrade of it, is going. Day1 logs who started what
   (`scale_started`, `scale_start_unconfirmed`); the orchestrator records
   nobody.

## Alternatives rejected

- **Computing the spread, or checking the balance, in Wingman**: that is
  the workflow's plan (`nodepool_replicas.plan`); a second copy drifts, and
  the run's result already shows it.
- **Kinds from every InfraEnv prefix**: `dell` would put a cluster's 660s
  and 760s in one total. Kinds from InfraEnvs on the MCE: they are the
  MCE's, not this cluster's.
- **NodePool names only from the MCE**: by-NodePool would then need live
  status, which some installs keep off; the file's names are the ones the
  workflow matches by.
- **Checking each endpoint for replicas** (the modify route, the sync
  route, …): a write path added later would forget it. Enforcing in the
  GitLab write itself: it cannot tell a person's YAML (refuse) from a sync
  (leave out), and a sync's preview would show a diff the MR does not have.
- **Refusing a sync that would restore replicas**: the rest of the sync
  (configs, tuning, the version) would wait for a person; holding replicas
  out lets it go and makes the restore an explicit, separate run.
- **Queuing restores in Wingman**: a second scheduler next to Temporal's;
  the orchestrator refuses a second run, and the page waits for the first.
- **A separate Scale page**: the NodePools are on the Nodes tab (one view
  per thing).

## Consequences

- Scales are commits to day1 `main` by the workflow, with no merge request:
  the approvals page does not see them; the History tab shows them
  (`nodepool(<cluster>): replicas a 3→4, … [<run id>]`).
- The workflow must read and write the same day1 repo as Wingman, and each
  MCE's server-lifecycle worker needs its `day1.*` values; without them a
  run fails at once with `Day1NotConfiguredError`, nothing read or written.
- Turning it on changes who writes replicas: a team that sized clusters by
  editing the file, or by syncing a flavor, now uses Scale or Restore.
  A pending MR that already changes replicas still merges (approving is not
  a write of the file), but a review edit of it must put them back.
- New metrics operation on `workflows`: `start_update_nodepool`; reading a
  run is `get_run`, twice while a child runs (`docs/ops/metrics.md`). No
  cluster, NodePool or kind in the labels.
- New problem code: `SCALE_ALREADY_RUNNING`.
- The contract is the workflow's branch until it merges; Wingman's adapter
  and parsing stay thin and tolerant, and a field it adds is ignored until
  Wingman reads it. The orchestrator's `error` is the root failure's
  message only: the type is shown when the words name one (a child's
  failure always does), else just the words.

## Verification

- `apps/day1-service/tests/unit/domain/test_replicas_ownership.py`: the rule
  for each case (a change by name, InfraEnv or position; the chart's default
  1; a new entry, a removed one, a reordering, a new cluster), the words, and
  `edit_problems` on and off, a review edit against main.
- `apps/day1-service/tests/unit/domain/test_scale.py`: names, InfraEnvs,
  locks, the kinds offered (siblings, never other hardware), the error type,
  and a sync's held-back replicas.
- `apps/day1-service/tests/unit/infrastructure/test_scale_workflow.py`: the
  start's exact body by kind and by NodePool, 202, 409 in its words, 422,
  504 and a lost answer, the run with its child's phase, a completed run's
  plan and chosen servers (the design page's example), a failed one, and the
  metrics; `test_fake_scale.py`: the fake's phases, plan, 409s and refusals.
- `apps/day1-service/tests/api/test_scale_api.py`: off 501, the options, by
  kind and by NodePool with the MCE and cluster filled by day1, a running
  child's phase, a failed run, RBAC, bodies refused before anything is sent,
  locks and the restore, a lost answer.
- `apps/day1-service/tests/api/test_replicas_ownership_api.py`: off an edit
  may change replicas; on a modify and a review edit are refused, a new and a
  removed nodepool and a create's review are not; a sync's preview, answer
  and MR, and a rollout's item and MR, leave replicas out and list them.
- `tests/repo/test_chart_env_contract.py`: the chart value, off for kept
  values, refused without `workflows.url` and when not a boolean.
- `apps/web/e2e/tests/cluster-scale.spec.ts`: hidden when off and for
  viewers; by kind and by NodePool post the right body; the run's phases,
  plan and chosen servers; a 409 and a failed run in words; a locked
  NodePool and a kind selecting one cannot be scaled; the sync's restore.

## Amendment (2026-11-16): each NodePool scales where it is shown

The user (2026-11-16) found the Scale dialog of decision 2 (two tabs, a
radio list, a typed total, a review step) heavy, and asked that a NodePool
scale where it is shown, with a hardware type's total apart, without making
the Nodes tab busier. The API, the workflow, the locks (4), the ownership
rule (5) and the run in place do not change; only the web's controls do.

- **On the NodePool's card.** Each card of the Nodes section (a NodePool as
  the MCE reports it, "2 / 3 ready") has, for an admin, a − N + stepper
  beside its ready count: the replicas the day1 file sets, matched to the
  card by NodePool name. It starts at them; the buttons and the arrow keys
  move it by one, and it can be typed. A change opens under the card's
  header: `Replicas 3 → 4 (+1)`, one line on what the run does, Cancel and
  Scale up or Scale down; it sends `{nodepool, replicas}`. A control that
  cannot act never looks editable: a NodePool its flavor locks (or whose
  replicas are not a number) has no stepper, only its size as text
  (`3 replicas`), the lock in one line under the header and its Restore
  beside it; a card the day1 file does not name has no stepper either.
  The stepper stays quiet (the number at full strength, the frame and the
  − + faint) until the card is hovered or the stepper focused, and always
  shows on a touch screen.
- **Without cards, on the NodePool sizes rows.** While live status is off
  (`CLUSTER_STATUS_ENABLED`), the MCE cannot be read or lists no NodePool,
  there are no cards: the same stepper and change sit on each row of the
  "NodePool sizes" panel. With cards, the panel folds to a line (how many
  NodePools and replicas the file sets) and keeps a row only for an entry no
  card shows, such as one the file cannot name, so no NodePool is editable
  twice.
- **A hardware type in a dialog.** "Scale hardware type", beside the
  NodePool sizes heading, opens a small dialog: the hardware types (the
  kinds the API offers) over two or more NodePools, one chosen, a locked one
  listed but not offered, with why and its total as text; a − N + total
  starting at its total now;
  the change (`6 → 8 (+2)`); Cancel and Scale up or Scale down. It sends
  `{infra_env_kind, replicas}`. With one NodePool a total would do what the
  NodePool's own stepper does, so such a type is not listed; with none over
  two, there is no button.
- **One change at a time** (one run per cluster): the cards, the rows and
  the dialog share one change. Changing a stepper makes it the change and
  puts every other back at its value now; a stepper set back to its value
  leaves nothing to send. The change is announced from one polite live
  region.
- **Scale-up starts at once** (guarded against a double click); **scale-down
  asks first**, in place (in the card, the row or the dialog). *Superseded
  later on 2026-11-16 (below): both ask first, in one confirmation.* The servers
  that leave are the NodePool's `redbull.io/scale-down-policy`'s, else
  CAPI's at random, and they stay in the MCE's inventory. Start scale-down
  waits half a second, so the click that asked cannot start it. Once a run
  starts, focus moves to the run, which shows under NodePool sizes as
  before.
- **While a run of the cluster is going** (scale or upgrade), no stepper
  shows: each size is text, the dialog's button waits, and the reason shows
  once, at the top of NodePool sizes; the waiting buttons point to it.
- **2026-11-16 (3.42.0): every scale is confirmed first** (the user: "a
  confirmation that gives a short explanation, like the uninstall workflow
  ... avoids unwanted scale up / scale down"). Scale up and Scale down, on a
  card, a row or in the hardware type dialog (over it, as its child: Escape
  closes only the confirmation), open one short dialog shaped like the
  uninstall's: `Scale up <NodePool or hardware type>?`, the change
  (`3 → 4 replicas (+1)`, or `5 → 7 in total over 2 NodePools; the workflow
  spreads it`), and a few lines from the workflow's design page. Up: each new
  node takes a free server of that hardware, or waits until one is added;
  one commit to day1 `main`, no merge request, which the workflow has Argo CD
  apply; done when the NodePool shows the new size, new nodes joining after
  they install. Down: which nodes leave by the NodePool's scale-down policy
  (`fewest-pods` the fewest pods, `least-requested` the lowest requested CPU
  or memory, `least-utilized` the lowest live use; without one CAPI picks at
  random; unhealthy machines always first), an unknown value shown as
  written with "the workflow will refuse it", each NodePool's when a
  hardware type's differ; their pods move to the remaining nodes and the
  servers stay in the MCE's inventory, free; one commit to day1 `main`,
  applied by Argo CD. No typed name: Cancel, or **Yes, scale up** (default)
  or **Yes, scale down** (destructive), armed after half a second. Cancel
  and Escape send nothing and leave the change where it was; a refusal shows
  in the confirmation, then under the change. The in-place scale-down
  question is gone. The policy is `GET .../scale`'s new per-NodePool
  `scale_down_policy`: the `nodepool[]` entry's
  `annotations["redbull.io/scale-down-policy"]` as written, else `null`
  (`docs/notes/2026-11-16-scale-nodepools-api.md`). One set by hand on the
  MCE's NodePool is not in the file; the run reads it, and its result shows
  the policy it used. A Restore keeps its own question in place.

Verification: `apps/web/lib/scale-model.test.ts` (the hardware types with a
total, a change in words, a typed number and a step);
`apps/web/lib/scale-confirm.test.ts` (the confirmation's lines: each
policy, none, an unknown one, a hardware type's alike or differing);
`apps/day1-service/tests/unit/domain/test_scale.py` and
`tests/api/test_scale_api.py` (the policy read from an entry's annotations);
`apps/web/e2e/tests/cluster-scale.spec.ts` (a card's stepper and a row's
post the exact body once, after the confirmation's Yes, armed after half a
second; a typed number and the arrow keys; one change at a time across rows
and the dialog; the confirmation's Cancel and Escape send nothing and keep
the change; a scale-down's lines for each policy, none and an unknown one;
the hardware type's confirmation over its dialog, each NodePool's policy,
Escape closing only it; a refusal in the confirmation; a locked NodePool on a row and on its card, as text with its
restore; a card the file does not name; the dialog's total and its
scale-down; a locked type as text, and no button without one; while busy no
stepper and one reason; a viewer sees no stepper).
