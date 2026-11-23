# ADR-0062: A hosted cluster's NodePools are scaled through the update-nodepool workflow, behind a setting, and while it is on their replicas change only that way

Date: 2026-11-16
Status: Accepted; amends ADR-0012 (who owns each NodePool's `replicas`), ADR-0037 and ADR-0044 (a sync's and a rollout's MR leave them out); amended 2026-11-16 (no Scale dialog: each NodePool scales on its card, a hardware type's total in a small dialog; then every scale confirmed first, with the scale-down policy); amended 2026-11-18 (one NodePool a run: the by-kind mode and the hardware type total removed, as the workflow did; then a scale-down may name the servers that leave; then it may choose its own policy instead, and a nodepool declares its own at create); amended 2026-11-19 (a 404 to the start is an orchestrator without update-nodepool, said so; Scale may be on before it is deployed); amended by ADR-0038 (2026-11-23: the Nodes tab, and so Scale's sizes and run, are an admin's; a viewer's run names no server); amended 2026-11-23 (on by default wherever the orchestrator is, since update-nodepool is in production; without one there is no Scale and nothing fails); amended by ADR-0042 (2026-11-23: the orchestrator is required, and Wingman opens no create MR, so a review edit is always held to the file on the target branch)

## Context

How many workers a hosted cluster runs is each `nodepool[]` entry's
`replicas` in its day1 file. Today a person changes it by editing the file
(the cluster page's YAML editor, an edit of a pending merge request), and a
flavor that locks `nodepools[<i>].replicas` (ADR-0026) sets it back through
a sync or a rollout's merge request (ADR-0037, ADR-0044). Nothing chooses
which servers leave on a scale-down: CAPI picks at random.

The platform team wrote the `update-nodepool` workflow (team-redbull/workflows,
branch `feat/update-nodepool`, designed with the operator 2026-11-03 and
2026-11-08; not merged then, merged and in production since: the
2026-11-23 amendment). `POST /workflows/server-lifecycle/update-nodepool`
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
   FEATURE_DISABLED` and nothing else changes. (*Since 2026-11-23 the
   default is `true`, and Scale is on only where the orchestrator is:
   without it there is none, and neither day1 nor the chart refuses it.
   The last amendment.*)
2. **Scale lives on the cluster page's Nodes tab**, where the NodePools are
   (no new page). A "NodePool sizes" panel lists the cluster file's
   NodePools on `main` (not the MCE's, so it works with live status off),
   an admin's **Scale** opens a dialog with the API's two ways, and the run
   shows in place for anyone signed in (*an admin only since 2026-11-23: a
   viewer has no Nodes tab, ADR-0038's amendment*):
   - **By hardware kind** (*removed 2026-11-18, below: the workflow takes
     one NodePool only*): a new total for the NodePools of one InfraEnv
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
   cannot either (*no kind since 2026-11-18*); day1 refuses both with a 422. The one move allowed is
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
- The contract was the workflow's branch until it merged (it is main since); Wingman's adapter
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
- **A hardware type in a dialog** (*removed 2026-11-18, below*). "Scale hardware type", beside the
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

## Amendment (2026-11-18): one NodePool a run

The workflow changed on its branch (team-redbull/workflows
`feat/update-nodepool`, b1976f4; the operator, 2026-11-18: "no need
infraenv kind"): a start always names `nodepool`, and `infra_env_kind` is a
422 that says to name the NodePool; a run recorded with a kind before then
still finishes as it began. Wingman follows it; the run, the locks (4) and
the ownership rule (5) do not change.

- **Wingman sends exactly `{mce_cluster, cluster, nodepool, replicas}`**
  (`scale_workflow._start_body`); `ScaleRequest`, `ScaleTarget` and
  `ScaleIn` have no other field, so nothing else can be sent. The by-kind
  mode is gone everywhere: `domain.scale.KindChoice`, `kind_choices` and
  `belongs_to_kind`; `GET .../scale`'s `kinds`; `POST .../scale`'s
  `infra_env_kind`; the fake's spread; the web's hardware type dialog, its
  total and the confirmation's lines for it. Decision 2's "By hardware
  kind", decision 4's kind that selects a locked NodePool and the first
  amendment's "A hardware type in a dialog" are superseded.
- **Day1 refuses a start it cannot map to one NodePool, before anything is
  sent** (amends decision 3, which left an unknown name to the workflow).
  A body with `infra_env_kind` is `422 VALIDATION_ERROR` in words ("send
  the NodePool's name as nodepool"), not an unknown-field error. A
  `nodepool` that no entry of the cluster file on `main` renders is a 422
  listing the file's NodePools: the workflow needs the NodePool in day1
  under that name, so its run could only fail. A name two entries render is
  a 422 too: the chart refuses that file. The workflow's own 422 stays
  `422 VALIDATION_ERROR` with its findings and "nothing was started".
- **A run recorded by kind is still read and shown**: its result keeps
  `infra_env_kind` (and `nodepool: null`), and the run card shows "Scale
  kind <kind>", its NodePools and the total, as before.
- **The result's `ignored`** (new in the workflow): what the request said
  about a scale-down that a run scaling up, or not at all, had no use for,
  in the workflow's words; never a failure. Day1 reads it
  (`ScaleResult.ignored`, `GET .../scale-run`'s `result.ignored`) and the
  run card lists it under "Not used: the run did not scale down". Wingman's
  own starts send nothing a run can ignore; a run of the cluster started
  elsewhere may.
- **`ScaleDownServersInvalidError`** (new in the workflow): the servers a
  scale-down request named cannot be the ones that leave; nothing is marked
  or written. It is a failed run like the others: its type and words show,
  and the run card adds a plain line under them.
- Naming the servers a scale-down removes (the workflow's new
  `server_names`) is not built here; it waits for the user's decision.
  *The user decided the same day: built, below.*

Verification: `test_scale_workflow.py` (the start's exact four fields; a run
recorded by kind still read, with its plan and chosen servers; `ignored`
read leniently), `test_fake_scale.py` (a scale-down and an unknown NodePool
by name), `tests/api/test_scale_api.py` (`infra_env_kind` refused in words,
a NodePool the file does not name and one two entries render refused, none
sent; the options have no `kinds`; the run's `nodepool`, `infra_env_kind`
and `ignored`), `apps/web/lib/scale-model.test.ts` (the start's body, a
run's target, the failure line), `apps/web/lib/scale-confirm.test.ts`, and
`apps/web/e2e/tests/cluster-scale.spec.ts` (no hardware type anywhere, a run
by kind still shown, a run's `ignored`, the failure line).

## Amendment (2026-11-18, later): a scale-down may name the servers that leave

The user (2026-11-18) asked that a scale-down let the admin pick which
servers leave, optionally: none picked keeps the NodePool's policy (or
CAPI) choosing, as before. The workflow takes it as `server_names` (b1976f4):
exactly those servers, as many as the replicas removed, each a Machine of the
NodePool; a scale-up or no change ignores it and says so in `ignored`.

- **The names are the workflow's.** It matches a named server to its
  Machine by AgentMachine → Agent → the Agent's
  `agent-install.openshift.io/bmh` label, else the Agent's hostname, else
  the Machine's Node, lowercased. Day1 already follows each Machine to its
  Agent for the Nodes tab (ADR-0038), so `GET .../nodes` gives each node a
  `machine_server` computed by that same rule (`machines.machine_server`),
  and that is what is sent. Not server-scan's records: server-scan places a
  server in a cluster, not in a NodePool, and its name reaches a Machine
  only through the BareMetalHost label the workflow reads first anyway.
  The `server_name` the page shows is server-scan's name when it knows the
  server, which can differ from the workflow's (a host found by MAC or
  serial, with no label); `machine_server` cannot. A Machine with no Agent
  and no Node has none and cannot be named.
- **Day1 checks only what is its own** (decision 3): `server_names` is 1 to
  20 server names, each once case-insensitively; it is sent only on a
  scale-down of the file's replicas on `main` (a scale-up or no change with
  names is a 422: never sent), and only exactly as many as leave (a 422 that
  says how many). Which Machine each name is, a server named twice on the
  MCE, an unhealthy Machine 4.18's CAPI would take instead, and an MCE
  worker too old for the field are the workflow's: a failed run,
  `ScaleDownServersInvalidError`, in its words.
- **The run shows them**: a named server's `chosen` entry has `policy:
  "named"` and its `server`.
- Documented by the workflow for OpenShift 4.19 and later; on 4.18 it
  refuses a pick CAPI could override.
- **In the web, in the scale-down's confirmation** (no new page, no new
  control on the card): the NodePool's Machines from the Nodes tab's read
  (`GET .../nodes`), each shown by server-scan's name (else the workflow's),
  its Node and state, with a checkbox. Optional: none ticked sends no names
  and the NodePool's policy line stays; ticking counts "1 of 2 picked: tick
  1 more, or none", the rest wait once as many are ticked as leave, and Yes
  waits while some but not all are; all ticked, the line says exactly those
  leave and the policy is not used. A Machine with no server yet, or one
  already deleting, is listed but cannot be ticked, with why. Without live
  status there is nothing to pick from, and it says so. Closing the
  confirmation drops the picks; changing the replicas does too. A scale-up
  shows none and never sends names.
- **The run**: a named server shows by its server, "picked by name". A
  `ScaleDownServersInvalidError` gets a line under the workflow's words that
  says, from those words, which refusal it is (a wrong count, a server
  picked twice, one that is no machine of the NodePool now, two machines
  that are one server, an unhealthy machine 4.18's CAPI would take instead,
  an MCE worker too old for names), else a general one.

Verification: `tests/unit/domain/test_machine_server.py` (the rule),
`tests/api/test_nodes_api.py` (`machine_server` in the nodes' contract),
`test_scale_workflow.py` (the names sent, a named `chosen` read),
`test_fake_scale.py` (exactly the named servers leave),
`tests/api/test_scale_api.py` (names sent on a scale-down; refused on a
scale-up, on no change, on a wrong count, twice, empty, more than 20, not a
list; none sent); `apps/web/lib/scale-servers.test.ts` (what can be picked,
the count's words, the line once complete), `apps/web/lib/scale-model.test.ts`
(the body with and without names, each refusal's line), and
`apps/web/e2e/tests/cluster-scale-servers.spec.ts` (none picked sends no
names; Yes waits for the count, then the workflow's names are sent; the
rest wait once all are picked; Cancel drops the picks; a scale-up offers
none; a Machine with no server or already leaving cannot be picked; without
the MCE's nodes it says so; the run's named server and a refusal's line).

## Amendment (2026-11-18, later still): a scale-down may choose a policy of its own, and a nodepool declares its own

The user (2026-11-18): "Let's perform the scale-down policy integration: it
can select the servers to be removed when scaling down, or override the
current scale-down policy declared inside the nodepool. Plus we need to make
it possible to declare it inside the nodepool, with the annotation, in
Wingman's create cluster and in hostedclusters-setup." The workflow takes
the override as `scale_down_policy` (b1976f4, aab8949): on a scale-down it
ranks the NodePool's Machines by that policy, ahead of the NodePool's own
`redbull.io/scale-down-policy` (even one of its own that is no policy), for
that run only; with `server_names` too it is a 422, and a scale-up or no
change ignores it and says so in `ignored`. The run, the locks (4) and the
ownership rule (5) do not change.

- **Which servers leave is one choice a scale-down makes**, and at most one
  answer is sent: the NodePool's own policy (sends nothing: the default, and
  without one CAPI picks at random), a policy for this run
  (`scale_down_policy`), or the servers picked (`server_names`, the
  amendment above).
- **Day1 checks what the workflow would refuse, before anything is sent**:
  `scale_down_policy` is one of the workflow's enum
  (`domain.scale_down_policy.ScaleDownPolicy`: `fewest-pods`,
  `least-requested`, `least-utilized`), and not beside `server_names`; both
  are `422 VALIDATION_ERROR` from the body. As for names, it is sent only on
  a scale-down of the file's replicas on `main`: on a scale-up or no change
  it is a 422 that says so, never sent, so Wingman's starts still send
  nothing a run ignores. `ScaleRequest`, `ScaleTarget` and `ScaleIn` gain
  the field; the start's body adds it only when set.
- **What the workflow says of each policy** (its design page): unhealthy
  Machines always go first, then Nodes missing, NotReady or cordoned;
  `fewest-pods` the fewest workload pods, `least-requested` the lowest share
  of CPU or memory its pods request, `least-utilized` the lowest live use,
  from the hosted cluster's `metrics.k8s.io`: without the metrics API the
  run fails, `NodeMetricsUnavailableError`, nothing marked or written. On
  OpenShift 4.18's CAPI a marked and an unhealthy Machine rank the same,
  which is why a policy takes the unhealthy ones first, in CAPI's order.
- **The run's result** already carries what was used: the NodePool's
  `scale_down_policy` is the policy applied (the request's, else its own;
  `null` when it named its servers or had none), each `chosen[].policy` the
  policy or `named`, and `ignored` what a run that did not scale down left
  unused. The fake ranks by the run's policy too, and lists one sent with a
  scale-up in `ignored`.
- The override needs the workflows release that has `scale_down_policy`
  (the one that has `server_names`): an older orchestrator forbids the field
  (422, nothing started).
- **In the web, in the scale-down's confirmation** (no new control on the
  card): one fieldset, **Which servers leave**, three radios, the chosen
  one's detail under it. **The NodePool's own policy** names it (or "the
  platform default: CAPI picks at random") and is the default; **Another
  policy for this run** opens a select of the workflow's policies but the
  NodePool's own (the first by default), with what it removes
  (`least-utilized` says it needs the metrics API); **Pick the servers**
  opens the picker of the amendment above, which is no longer optional once
  chosen: Yes waits for exactly as many as leave. Without the MCE's nodes it
  cannot be chosen, and says why; a failed nodes read is read again by the
  Nodes tab's Retry only, never by the confirmation opening, and the sizes'
  rows stay while it is (2026-11-20: a 404 read again on each opening
  unmounted the open confirmation, which opened again, in a loop). The
  confirmation's main line follows the
  choice ("…(least-requested, for this run only)"), and an unknown policy of
  the NodePool's own is still said to be refused, with another policy the
  way out. Changing the choice drops the ticks; Cancel, Escape and a new
  number drop the choice. A scale-up shows none and sends neither
  (`lib/scale-leave.ts`: what is sent, when Yes waits, the line).
- **The run says which way its servers were chosen** ("Which servers
  left"): picked by name; by the NodePool's own policy, when the applied
  policy is the day1 file's; by another ("not the day1 file's policy (…):
  this run's choice, or one set on the NodePool itself", since the result
  does not say which, and the orchestrator does not return the request); or
  at random by CAPI. A run that did not scale down says nothing, and lists
  what it ignored as before.

### A nodepool declares its own policy

The NodePool's own policy is its `redbull.io/scale-down-policy` annotation,
which the hostedclusters-setup chart renders from the `nodepool[]` entry's
`annotations` map, as written (`toYaml`), after the chart's own
`argocd.argoproj.io/sync-wave` (a change to `templates/nodepool.yaml`,
approved by the chart's owner, not merged upstream yet; the air-gapped chart
gets it from a separate package). Wingman reads it
there since 3.42.0; now it writes it too. It is day1's create path, not
Scale's: it works whether Scale is on or off, and needs no setting.

- **The template input is `nodepools[].scale_down_policy`**, one of the
  workflow's three or none. The shared template writes it only when given:

  ```jinja
  {% if np.scale_down_policy | default("") %}
      annotations:
        redbull.io/scale-down-policy: {{ np.scale_down_policy }}
  {% endif %}
  ```

  None writes nothing: the platform default, CAPI at random. Any other
  value is refused at a create and at a flavor's save
  (`scale_down_policy.input_problems`).
- **A flavor presets or locks it** (ADR-0026's amendment):
  `nodepools[<i>].scale_down_policy` → `nodepool[<i>].annotations
  ["redbull.io/scale-down-policy"]`, compared as text; a lock fixes a
  policy, never none (a lock to none would have a sync delete keys). Drift
  lists it under that file key, and a sync or a rollout's MR writes it in
  the file's text as the template does (`cluster_text.set_annotation`:
  added at the entry's end, or its line replaced; the entry's other
  annotations and comments stay).
- **The stale-template guard** (ADR-0063, ADR-0064): a flavor that gives the
  input is refused while the specs project's template does not read it,
  and a create whose rendered file does not hold the annotation as given,
  or holds one unasked, is refused (`rendered_file`). The form schema offers
  the input only when the template reads it.
- **Edits keep it.** Every edit, sync and rollout keeps an entry's
  `annotations` byte for byte, and an edit (the YAML editor, a review edit)
  may set the policy only to one the workflow knows
  (`scale_down_policy.edit_problems`, in `cluster_file.edit_problems`): an
  unknown value the file already holds is left to the workflow. The chart
  does not refuse an entry's own `argocd.argoproj.io/sync-wave`, which would
  reach the NodePool twice; Wingman never writes it, and refuses an edit
  that adds it to an entry's `annotations`. Changing
  the annotation rolls no node: HyperShift does not roll a NodePool for its
  metadata.
- **The web** reads the template schema as the switch, as for the other
  newer inputs. The create form has a **Scale-down policy** select per
  nodepool: the platform default (sends nothing) or one of the three, each
  explained in a line; a flavor's locked one is read only. The flavor
  editor has it on each nodepool card as a preset or locked (a lock without
  a policy says it cannot be locked). In Edit cluster, **Scale-down policy
  per nodepool** sits above the YAML when the template writes the input or
  a nodepool already has one: it edits only the annotation's line in the
  file's text, as the template writes it, every other line kept, and leaves
  a flow-style `annotations` or a quoted key to the person
  (`lib/nodepool-policy.ts`).
- The workflow also reads a label or an annotation set by hand on the MCE's
  NodePool (Argo CD leaves an annotation it never set alone); the file
  cannot show those.

Verification: `test_scale_workflow.py` (the body with a policy and nothing
more), `test_fake_scale.py` (a run's policy ranks ahead of the NodePool's;
one sent with a scale-up is ignored and said so), `test_scale.py` (the
enum), `tests/api/test_scale_api.py` (a policy sent on a scale-down and
applied; an unknown one, and one beside named servers, refused from the
body; one on a scale-up or no change refused in words; none sent);
`apps/web/lib/scale-leave.test.ts` (the policies offered, what is sent for
each choice, when Yes waits, the line, the run's choice),
`apps/web/lib/scale-model.test.ts` and `scale-confirm.test.ts` (the body,
the line for this run), `apps/web/e2e/tests/cluster-scale-policy.spec.ts`
(the own policy named and sent as nothing; another one offered without the
own, said, and sent alone; the platform default; an unknown own policy and
the way out; Cancel and a scale-up; the run's choice each way) and
`cluster-scale-servers.spec.ts` (picking as a choice: Yes waits, another
choice drops the ticks, no choice without the MCE's nodes);
`tests/unit/domain/test_scale_down_policy.py` (the input, the template
guard, the rendered check, the lock, the edit rule),
`tests/unit/domain/test_cluster_text.py` (the annotation written as the
template does, in place, beside other annotations, from `{}`; a flow
mapping refused; every other edit keeps it), `test_locks.py` and
`test_template.py` (the lockable table, the fixture's schema),
`tests/api/test_scale_down_policy_api.py` (the schema, a create with and
without, an unknown policy, a stale template refusing a create and a
flavor, a preset, a lock to none refused, a locked policy's drift and sync,
an edit); `apps/web/lib/nodepool-policy.test.ts` (the schema switch, the
platform default left out of the request, the file's text edit: added as
the template writes it, replaced with its comment, removed with an empty
block, beside other annotations, a flow mapping or a quoted key left to the
person) and `apps/web/e2e/tests/nodepool-scale-down-policy.spec.ts` (the
create form with and without the input, the default sending nothing, a
locked policy read only; the flavor editor's preset and lock; Edit
cluster's policy per nodepool in the file's text, a file's own policy
without the input, a flow mapping refused).

## Amendment (2026-11-19): a 404 to the start is an orchestrator without update-nodepool

The workflow was not merged or deployed yet (it is since: the 2026-11-23
amendment). The user (2026-11-19): send
the start to its path now; it answers 404 today, and once the workflow is
deployed the same request answers 202, with no change in Wingman. Scale
sends the same start to every orchestrator. Only how a 404 reads changes.

- **The start route never answers 404 itself.** On `feat/update-nodepool`
  (aab8949) it answers 202, 409 (a run of the cluster, or an upgrade of it,
  is running), 422 (the body) and 500 for a Temporal error it does not
  expect. An unknown cluster or NodePool is a FAILED run
  (`ClusterNotOnMceError`, `NodePoolNotFoundError`, …), and an MCE with no
  worker gives a run that waits. Neither is a 4xx. So a 404 is FastAPI's
  own answer for a path it has no route for, whose whole body is
  `{"detail": "Not Found"}`: an orchestrator with no update-nodepool yet.
- **That 404 is `502 DEPENDENCY_UNAVAILABLE`.** It raises
  `WorkflowsUnavailableError`, the existing "nothing was started" error
  (metrics outcome `unavailable`), in these words: "update-nodepool is not
  deployed on this orchestrator yet (it has no POST
  /workflows/server-lifecycle/update-nodepool): nothing was started for
  <cluster>. Scaling works as soon as the workflow is deployed there, with
  no change to Wingman." Before, it read "the orchestrator refused the
  scale of <cluster> (404): Not Found", as if the orchestrator had judged
  the request. Any other 404 is still a refusal in the orchestrator's own
  words: a body with other words or other fields, or a page from a router
  in front. So a real refusal is never reported as "not deployed". There
  is no new problem code. The web's heading for a 502 start is now neutral
  ("Nothing started: the workflows orchestrator could not start
  update-nodepool."), and the words under it say which case it is. It is
  not `501 FEATURE_DISABLED`, which means a Wingman setting is off and is
  read that way by the web.
- **Scale loads meanwhile.** Its options come from the day1 file. Its run
  is `GET /workflows/runs/update-nodepool-<cluster>`, a route every
  orchestrator has, which answers 404 for a run that never existed, so the
  page shows "no run". Only pressing Scale (or a Restore) shows the words.
- **Scale may be turned on before the workflow is deployed**
  (`day1.scaleNodepools.enabled`). Decision 5 then applies at once:
  - an edit that changes an existing NodePool's replicas is refused, and
    points to Scale;
  - a flavor's sync or rollout leaves drifted locked replicas out of its MR
    and offers a Restore, which starts update-nodepool too.

  So until the workflow is deployed, nobody can change an existing
  NodePool's replicas from Wingman. Three things still work: a new
  cluster's and a new `nodepool[]` entry's first replicas, removing an
  entry, and merging an MR that was opened earlier and already changes
  them (approving is not a write of the file). The upgrade guide says this
  (`docs/upgrade/3.39-to-3.40.md` step 3.1).

Verification: `test_scale_workflow.py` (FastAPI's 404 is "not deployed",
with its exact words and the outcome `unavailable`, and the run reads as
none; a 404 with other words, other fields or an HTML page is a refusal
in its words); `tests/api/test_scale_api.py` (an orchestrator without
update-nodepool: `GET .../scale` 200, `GET .../scale-run` `404 NOT_FOUND`,
`POST .../scale` `502 DEPENDENCY_UNAVAILABLE` with the words);
`apps/web/e2e/tests/cluster-scale.spec.ts` (the tab loads with no run,
and the confirmation shows the heading and the words).

## Amendment (2026-11-23): on by default wherever the orchestrator is

The user (2026-11-23): "now the scale is production so you can make it
turned on by default". update-nodepool is merged in team-redbull/workflows
and runs in production, so from 3.53.0 Scale is on by default.

- **The default is `true`**: `DAY1_SCALE_NODEPOOLS` and the chart's
  `day1.scaleNodepools.enabled` (decision 1). `false` still turns it off.
- **Scale needs the orchestrator. Without one there is no Scale, and
  nothing fails.** One switch, `Day1Settings.scale_nodepools`, is what
  everything reads: the routes, the adapter and decision 5's replicas
  rule. It is on when `DAY1_SCALE_NODEPOOLS` is true and there is an
  orchestrator (`WORKFLOWS_API_URL`, or `DAY1_FAKE_FLEET` in development).
  - Day1 no longer refuses to start with `DAY1_SCALE_NODEPOOLS=true` and
    no `WORKFLOWS_API_URL`: that is now the default. It means no Scale:
    the routes answer `501 FEATURE_DISABLED`, whose words now say
    "DAY1_SCALE_NODEPOOLS=false, or no WORKFLOWS_API_URL", and an edit may
    change replicas, as before.
  - The chart no longer fails on `enabled` without `workflows.url`. It
    renders `DAY1_SCALE_NODEPOOLS` as `"true"` only with `workflows.url`,
    else `"false"`. Values kept from a release before 3.40 (no
    `scaleNodepools` map) take the default, as `placementMinFreePods` does.
  - So a default install without the orchestrator renders, starts and
    behaves as before.
- **Why not keep refusing an explicit `true` without the orchestrator**,
  as `DAY1_UPGRADES` and `DAY1_ADD_SERVERS` do: neither day1 nor Helm can
  tell an explicit `true` from the default, and the default install must
  still render and start. Upgrades and adding servers stay off by
  default, and keep their refusal.
- **Everything Scale does while it is on is unchanged**:
  - an edit (the YAML editor, a review edit) that changes an existing
    NodePool's replicas is refused and points to Scale;
  - a flavor's sync and a rollout's MR leave drifted locked replicas out,
    list them in `held_replicas` and offer Restore with update-nodepool;
  - a locked NodePool moves only back to its value, and one run per
    cluster;
  - a new cluster, a new `nodepool[]` entry and removing one are left
    alone.
- **On upgrade, an existing deployment with `workflows.url` gets Scale**
  unless its values set `enabled: false`. A values file copied from an
  older chart's `values.yaml` does set it, and so does `--reuse-values`,
  which keeps the old release's default. `--reset-then-reuse-values`, which
  every upgrade guide uses, takes the new default.
  `docs/upgrade/3.52-to-3.53.md` checks first that update-nodepool is on
  the orchestrator and on every MCE's worker, or turns Scale off. An
  orchestrator without it reads "not deployed yet" (the 2026-11-19
  amendment), and then nobody changes an existing NodePool's replicas from
  Wingman.
- **A NodePool's own scale-down policy still needs the hostedclusters-setup
  chart patch 0001** (`docs/upgrade/patches/hostedclusters-setup/`).
  Without it a nodepool entry's `annotations` never reach the NodePool, and
  a scale-down picks by a policy set on the NodePool by hand, else CAPI at
  random. Scale itself does not need it. Neither does a policy for one run
  (`scale_down_policy`) or picking the servers.

Verification: `apps/day1-service/tests/unit/test_compose_scale.py` (the
default; on with an orchestrator or the fake fleet; off without one, whatever
the setting says, and when turned off; the workflow keys follow; the adapter
built by default, none when off); `tests/unit/test_main.py` (the
orchestrator's adapters include update-nodepool's by default);
`tests/api/test_scale_api.py` (on by default beside the orchestrator; `501`
without one and when turned off, nothing started);
`tests/api/test_replicas_ownership_api.py` (on by default an edit of
replicas is refused; turned off beside the orchestrator it is not);
`tests/repo/test_chart_env_contract.py` (on with `workflows.url`, also for
kept values; off without it, with no failure, whatever the value; off when
`false`; a value that is not a boolean refused).
