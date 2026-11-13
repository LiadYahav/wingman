# ADR-0055: Upgrade a hosted cluster through the upgrade-cluster workflow, behind a setting

Date: 2026-11-13
Status: Accepted; amends ADR-0012 (who owns `mastertag`, `workertag` and `pausedUntil`)

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
     (ADR-0034's read stays for a new cluster's versions only).
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
