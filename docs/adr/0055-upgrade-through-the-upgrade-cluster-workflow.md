# ADR-0055: Upgrade a hosted cluster through the upgrade-cluster workflow, behind a setting

Date: 2026-11-13
Status: Accepted; amends ADR-0012 (who owns `mastertag`, `workertag` and `pausedUntil`); amended 2026-11-13 (3.19.0: the fleet's upgrades on the Clusters page; 3.20.0: upgrades inside the clusters list, its Upgrades view removed)

## Context

A hosted cluster's version is its file's `mastertag` (and a NodePool's
`workertag`). ADR-0012 gives them to people and Wingman: a modify, or an MR
review edit, may change them freely. Hand-editing `mastertag` skips
everything an upgrade needs: the ladder's minor-by-minor path, the digest
pins, the admin acks, the day2 confirm, one NodePool at a time.

The platform team has the `upgrade-cluster` workflow, started through the
workflows orchestrator
(`docs/notes/2026-11-13-upgrade-cluster-workflow-api.md`). It plans the path
along the day1 repo's ladder, pre-flights, waits for one approval with
nothing committed, then commits `mastertag`, each `nodepool[].workertag`,
`inPlace.maxUnavailable` and, on an abort, `pausedUntil` straight to day1
`main`, one step at a time, waiting for people between steps (`confirm-day2`,
`continue`). Its decisions are Temporal Updates judged by the run's own
validators. Its own page on the orchestrator is temporary until a platform
UI exists; Wingman is that UI.

The limbs are on the sandbox only, "not in production yet".

## Decision

1. **`DAY1_UPGRADES`** (default `false`) turns upgrades on. It needs
   `WORKFLOWS_API_URL`; day1 refuses to start without it (ADR-0009). The
   chart sets it from `day1.upgrades.enabled`. Off, the upgrade routes
   answer `501 FEATURE_DISABLED` and the web shows nothing.
2. **Start, show and decide, all on the cluster page.** No new page.
   - An admin's **Upgrade** on the Overview's Mastertag row opens a dialog
     fed by the workflow's `upgrade-targets` (its own timeout,
     `WORKFLOWS_TARGETS_TIMEOUT_SECONDS`, 65 s: the orchestrator waits up to
     60 s). The dialog says that Start plans and checks, then waits for
     approval, with nothing committed before it.
   - An **Upgrade panel** on the Overview shows the cluster's newest run,
     read by its id `upgrade-cluster-<file stem>`: its status, its phase
     humanized, `waiting_for` verbatim, the plan's steps, the agent's
     verdict and proposals, the log, the error. The current NodePool links
     to the Nodes tab (ADR-0038). Any signed-in user may read it.
   - Admins press its decisions: approve, approve-admin-ack, continue,
     confirm-day2, pause, resume, abort (a reason required), retry, and
     approve or reject an agent's proposal.
   - Day1 fills `requested_by` and `by` from the signed-in user, never from
     the request, and logs who did what.
3. **Wingman keeps no copy of the workflow's logic.**
   - No phase list: the phase is the workflow's word, humanized.
   - No targets of its own: the ladder is read by the workflow
     (ADR-0034's read stays for a new cluster's versions only; since 3.20.0
     it also feeds the clusters list's "Upgrade available", a suggestion
     Wingman never sends as a target).
   - Which buttons to draw: the run's `progress.decisions` once it carries
     it. Until then one small map in the web, phase → decisions, the same as
     the orchestrator page keeps (`awaiting-approval` → approve,
     `awaiting-day2-confirm` → confirm-day2, `awaiting-admin-ack` →
     approve-admin-ack and retry, `awaiting-continue` → continue,
     `needs-human` → retry and the pending proposals), with pause or resume
     and abort while the run is open. An unknown phase shows `waiting_for`
     and only pause and abort.
   - The run's validators judge every decision; a refusal (`409
     UPGRADE_DECISION_REFUSED`) is shown in the workflow's own words.
4. **Versions belong to the workflow while it is on (amends ADR-0012).**
   With `DAY1_UPGRADES` on, a modify or an MR review edit that changes
   `mastertag` or any `workertag`, or adds or changes `pausedUntil`, is
   refused: "Versions change through Upgrade on the cluster page". It is
   key ownership, like the automation keys, not a copy of the workflow's
   checks, and it lives in one domain rule
   (`wingman_day1.domain.upgrades.version_problems`) that `edit_problems`
   applies.
   - Removing `pausedUntil` stays allowed: after an aborted upgrade, nothing
     in the workflow clears it, a person does.
   - A new NodePool may carry a `workertag` only equal to the version it
     would follow without one.
   - Create still writes the starting `mastertag` (ADR-0034), and a review
     edit of a create MR may change it: that cluster does not exist yet.
   - With the setting off, nothing changes.
5. **Writes are never retried (ADR-0006).** A start or a decision sent and
   not answered, or the orchestrator's decision 504 (the Update may have
   landed), is `504 AMBIGUOUS_WRITE`: read the run first. A second start
   while a run is open is `409 UPGRADE_ALREADY_RUNNING`; targets the file or
   the rules refuse are `409 UPGRADE_TARGETS_REFUSED`.
6. **A port, an adapter and a fake (ADR-0001).** `UpgradeWorkflow` in
   `ports.py`; `HttpUpgradeWorkflow` beside the provision and uninstall
   adapters, sharing their client rules; `FakeUpgradeWorkflow` for
   `DAY1_FAKE_FLEET`, whose runs walk scripted phases from
   `dev/fleet-fixtures/upgrade.yaml` on the injected clock.

## Alternatives rejected

- **A page of upgrades** (the orchestrator page's runs list): the thing
  upgraded is one cluster and the run id is per cluster; a fleet view would
  be a filter on the clusters list, later.
- **Computing targets from the ladder in Wingman**: that is the workflow's
  path resolver; a second copy drifts when it changes.
- **Parsing the decision names off `waiting_for`**: it is prose, not a
  contract (`"continue, once ..."` uses a comma).
- **Blocking Wingman's merge requests while an upgrade runs**: the workflow
  protects itself (its compare-and-set stops at the next commit, its sync
  refuses someone else's change) and asks a person; a second copy of that
  rule in Wingman would drift. Warning about it is an open question.
- **Leaving `mastertag` editable**: an edit would skip the ladder, the pins,
  the acks and the day2 confirm, and the workflow's next compare-and-set
  would stop on it.

## Consequences

- Upgrades are commits to day1 `main` by the workflow, with no merge
  request: the approvals page does not see them. The History tab shows the
  commits (`upgrade(<cluster>): ... [upgrade-cluster-<cluster>]`).
- The workflow must read and write the same day1 repo as Wingman: a Wingman
  on a copy of day1 gets 404s from the targets, or upgrades the original's
  clusters (`docs/upgrade/3.15-to-3.16.md`).
- With upgrades on, a version mistake is fixed through an upgrade, not an
  edit; a person still clears `pausedUntil` after an aborted one.
- New metrics operations on `workflows`: `upgrade_targets`,
  `start_upgrade`, `decide_upgrade` (`docs/ops/metrics.md`); no decision
  name and no cluster in the labels.
- New problem codes, append-only (ADR-0004): `UPGRADE_ALREADY_RUNNING`,
  `UPGRADE_DECISION_REFUSED`, `UPGRADE_TARGETS_REFUSED`.

## Verification

- `apps/day1-service/tests/unit/infrastructure/test_upgrade_workflow.py`:
  against a mocked transport, the start (202, 409, 422, unanswered 504, an
  unreachable orchestrator), the decisions (200, 409, 404, 504, the body
  each takes), the targets (200, an empty list, 404, 409, 504), the run read.
- `apps/day1-service/tests/unit/infrastructure/test_fake_upgrade.py`: the
  fake's run walks its scripted phases on the clock, decisions advance it,
  a wrong one is a 409.
- `apps/day1-service/tests/unit/domain/test_upgrades.py`: the version rule.
- `apps/day1-service/tests/api/test_upgrades_api.py`: the routes, RBAC,
  `by` from the user, 501 when off, and modify and review edits refused only
  while on.
- `apps/web/e2e/tests/cluster-upgrade.spec.ts`: the dialog's targets, start,
  a run waiting for approval, approve, a refused decision's words, abort
  with a reason, and nothing shown when upgrades are off.

## Amendment (2026-11-13, 3.19.0): the fleet's upgrades on the Clusters page

*Partly superseded by the 3.20.0 amendment below: the Upgrades view and its
tab are gone, and the "Upgrading" badge became each row's upgrade state. The
run list, its cache, dismiss and the fake's demo runs stand.*

The user: "The upgrade panel should be inside clusters, no?" With upgrades
off on the sandbox, nothing showed at all, and nothing listed the fleet's
upgrades the way the orchestrator's own `/ui/cluster-upgrade` page does.
The alternative rejected above ("a fleet view would be a filter on the
clusters list, later") is now built, as a view of the Clusters page.

- **`GET /api/day1/upgrades`** (any signed-in user; 501 while
  `DAY1_UPGRADES` is off, like every upgrade route). One read of the
  orchestrator's run list, `GET /workflows/runs?workflow_type=UpgradeClusterWorkflow&limit=200`,
  folded to **one row per cluster**: its newest upgrade, the
  `continued_as_new` segments of that upgrade joined and started when the
  first of them started (the run continues-as-new after every step; the id
  is reused by the next upgrade). Open upgrades first, then the newest. The
  first 25 rows are read by id for the phase, `waiting_for`, `paused` and
  the outcome, as the orchestrator's page reads its newest 25; the rest carry
  the list's status only. Every row says where day1 has the cluster's file
  (`site`, `mce`), or `null` when it has none.
- **Cached, not every run read on each poll.** The list and those reads are
  kept 10 s per replica (ADR-0011), the TTL of Inventory's add-server runs,
  through `CachedUpgradeWorkflow`; a start or a decision through day1 drops
  them. A cluster's own Upgrade panel still reads its run uncached, so a
  decision shows at once. No new metrics operation: the list is `list_runs`,
  the reads `get_run`.
- **The Clusters page has two views**, Clusters and Upgrades, as tabs under
  its heading, the second at `/clusters#upgrades` (a hash, so Back returns to
  it and the page needs no Suspense boundary for a query parameter). A view,
  not a filter: its rows are runs, not clusters (a finished run, and a run
  on a cluster this day1 repo lacks, are listed too), and its columns are
  the run's: the status, the workflow's phase made readable, `waiting_for`
  verbatim (cut at a word, the whole text in a tooltip) and when it started.
  Each row links to its cluster's page. **No decisions in the list**: the
  cluster page's panel keeps the plan, the log and the decisions (one view
  per thing).
- **The clusters list** marks each cluster whose upgrade is open with an
  "Upgrading" badge beside its mastertag, from the same query; its tooltip
  says the phase and what the run waits for, and it opens the cluster.
- **Off, admins learn it exists**: no tab and no badge for anyone, and on the
  cluster page an admin sees Upgrade greyed out, its tooltip "Upgrades are
  off on this Wingman (DAY1_UPGRADES=false)."; a viewer sees nothing.
- **A finished run's panel can be dismissed**, in this browser only (a
  per-viewer convenience, as the tables keep their hidden columns). What is kept
  is the run's fingerprint (its id, outcome, target and last log line), so
  the cluster's next upgrade, under the same id, shows again.
- **The fake fleet** starts three demo runs (`demo:` in
  `dev/fleet-fixtures/upgrade.yaml`): one waiting for approval, one for the
  day2 confirm, one cancelled.

Alternatives rejected:
- **A filter on the clusters list** ("upgrading"): its rows are clusters and
  its columns the file's; the run's phase, `waiting_for` and start would be
  new columns on every row, and finished runs would have no row.
- **A separate `/upgrades` page**: the user wants it inside Clusters, and the
  run belongs to one cluster.
- **Reading every run by id on each poll**: one orchestrator read per
  cluster per viewer every 15 s. The list is one read; 25 cached reads at
  most.
- **Decisions in the list**: two places to decide one run would drift; the
  panel has the plan the decision is about.

Verification: `tests/unit/domain/test_fleet_upgrades.py` (the fold);
`tests/unit/infrastructure/test_upgrade_workflow.py` (the run list's request
and answers) and `test_fake_upgrade.py` (the fake's list and demo runs);
`tests/api/test_fleet_upgrades_api.py` (off 501, a session, an empty list,
the rows with phase and place, a cluster day1 lacks, the cache dropped by a
start and a decision, 502); `apps/web/lib/fleet-upgrades.test.ts` and
`upgrade-dismiss.test.ts` (Vitest); `apps/web/e2e/tests/clusters-upgrades.spec.ts`
(the view, the badge, empty, unreachable, Back) and `cluster-upgrade.spec.ts`
(greyed out when off, dismiss). 2026-11-13: the stack with
`DAY1_FAKE_FLEET=true DAY1_UPGRADES=true` and live status off lists the
fake's runs on `/clusters#upgrades`.

## Amendment (2026-11-13, 3.20.0): upgrades inside the clusters list, and a suggestion

The user: "I want to unite the upgrade cluster within the existing cluster,
also suggest him Upgrade! Because the customer will see his clusters only
and will press on it." One view per thing: a cluster's upgrade is part of
its row, not a second list of runs.

- **No Upgrades view.** The tab, `/clusters#upgrades` and its table are
  removed. `GET /api/day1/upgrades` stays: the list reads it (one query every
  row shares, every 15 s) for each open run.
- **Each row's upgrade, under its mastertag**, and nothing when up to date:
  - **Upgrading · <phase>**: the open run's phase made readable (Paused when
    paused; just "Upgrading" before the run is read); `waiting_for` verbatim
    in its tooltip. It links to the cluster page, whose panel keeps the plan,
    the log and the decisions. An open run wins over a suggestion.
  - **Upgrade available → <version>**: the cluster's MCE offers a newer
    release than its `mastertag`. "Offered" is ADR-0034's list, the one the
    create form uses: the ladder's rungs in the minors the MCE hosts. The
    tooltip says no more than that: the workflow plans the path, and may
    offer other targets, or none (the dialog then says "Nothing newer to
    offer").
- **The rule is day1's**, where the version comparison already lives
  (`bare_release`, numeric order): `upgrade_hint(mastertag, offered)` in
  `wingman_day1.domain.openshift_versions`, the newest offered release newer
  than the mastertag, `None` when there is none or the mastertag is not a
  release. `GET /api/day1/clusters` carries it as `upgrade_available` while
  upgrades are on (`null` otherwise): the ladder and each MCE's rules read
  once per list from the cached day1 repo (ADR-0035), nothing per row, and
  nothing from the orchestrator, so the suggestion stays when the
  orchestrator is down. It is a suggestion, not a target: this is not the
  rejected "computing targets from the ladder in Wingman" above, since
  Wingman never sends it and never plans with it.
- **Upgrade from the row.** An admin's **Upgrade** beside the suggestion
  opens the cluster page's dialog (the same component) in place: it asks the
  workflow for its targets as before. After a start the row shows
  "Upgrading" at once (the started run replaces the cluster's row in the
  fleet query until its next read). The cluster page keeps its Upgrade and
  its panel.
- **Who may press it.** Starting stays `AdminUser`: a viewer sees the
  suggestion and the state, with no Upgrade. The user wants customers to
  press it once each sees only their own clusters; with per-team RBAC
  (single-pane workstream 8) the start permission moves to the cluster's
  owners, and the row's button follows that check.
- **An Upgrades filter** beside Site and Drift, in their style (one shared
  pill component now): All, Upgrade available, Upgrading, with counts, shown
  only while upgrades are on. It is kept in the URL (`?upgrade=available`,
  `?upgrade=upgrading`), replacing the old view's shareable link; a change
  replaces the history entry, as the Segments page's filters do. The list's
  other filters are still the page's state. When the run list cannot be read,
  the filter carries a warning saying no row can show Upgrading.
- **Off** (`DAY1_UPGRADES=false`): no `upgrade_available`, no state, no
  button, no filter; the cluster page's greyed-out Upgrade is unchanged.

Alternatives rejected:
- **The rule in the web**, reading `GET /mces/{mce}/openshift-versions`
  per MCE: one request per MCE per list, and a second copy of the release
  order.
- **The suggestion in `GET /api/day1/upgrades`**: it would vanish whenever
  the orchestrator does not answer, though it needs nothing from it.
- **Asking the workflow's `upgrade-targets` per row**: a Temporal run per
  cluster per view.
- **"Upgrade to <version>" as the button**: the workflow may offer another
  target; the button opens its targets.

Verification: `tests/unit/domain/test_upgrade_hint.py` (the rule);
`tests/api/test_fleet_upgrades_api.py` (off: every hint `null`; on: the
fixtures' hints, none when up to date or ahead of the MCE, none for an MCE
without its rules file, and none of it needs the orchestrator);
`apps/web/lib/fleet-upgrades.test.ts` (Vitest: a row's state, the counts and
the filter, the URL, the started run); `apps/web/e2e/tests/clusters-upgrades.spec.ts`
(the suggestion and its tooltip, Upgrading with `waiting_for`, Upgrade from
the row opening the dialog and the row then Upgrading, the workflow offering
nothing, a viewer without a button, the filter in the URL, the run list
unreadable, off, and the old view gone). 2026-11-13: the stack with
`DAY1_FAKE_FLEET=true DAY1_UPGRADES=true` shows "Upgrade available" on the
clusters whose MCE offers newer, and "Upgrading" for the fake's open runs.
