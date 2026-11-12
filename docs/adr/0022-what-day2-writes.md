# ADR-0022: day2 writes the minimum per change, never pins a version per cluster by default, and says that removal orphans

Date: 2026-11-07
Status: Accepted; superseded in part by ADR-0053 (Wingman edits `exclusions.yaml` in place)

## Context

In the gitops-day2 layout a file's presence and keys have platform-wide
effects the legacy service ignored:

- a `targetRevision` in a cluster's `<chart>.yaml` is an **emergency pin**:
  it detaches that cluster from the team default and from `ocp-versions/`
  pins for good. The legacy service wrote one whenever the chosen version
  differed from its idea of the default (`main`, where the platform says
  `HEAD`);
- a chart folder for a chart that is also a fleet default generates the same
  app twice (the XOR rule);
- deleting a chart folder deletes the Application but **orphans** the
  workload (`prune: false`, no resources-finalizer); and deleting a cluster's
  last folder de-registers the cluster, orphaning the team's fleet defaults
  on it too;
- leaf apps are manual-sync: nothing deploys after a merge until someone
  syncs, and Wingman has no ArgoCD access.

## Decision

Every change is one MR on the team's repo, titled through core `mr_title`
(`[Wingman/Day2] Install|Update|Remove addon <team>/<chart>[,<chart>] on|from <cluster>`),
labelled `wingman`, `day2`, `<action>`, from a `platform/<user>/...` branch.

- **Install** creates `<cluster folder>/<chart>/values.yaml`, and
  `<chart>.yaml` only when the cluster needs a key the inherited config
  lacks: a `repourl` when no layer has a lowercase one (refused otherwise), a
  `projectNamespace`, or a `targetRevision` the caller asked for explicitly
  with `emergency_pin` (refused without it, warned with it). Refused when the
  chart is a fleet default of that kind and the cluster is not excluded.
  Notes say what else the new folder registers (the team's fleet defaults).
- **Update** rewrites the values file guarded by the caller's
  `last_commit_id` (ADR-0006); a fleet default is tweaked in
  `defaults/<scope>/<chart>/values-<cluster>.yaml` instead; the pin changes
  only when asked (setting the inherited version removes the pin).
- **Remove** deletes every file of the chart folder, guarded, and adds a
  `.gitkeep` when the cluster folder would disappear. A fleet default is not
  removed per cluster: the answer points at `exclusions.yaml` (runbook R10).
  Every remove says the workload keeps running and how to tear it down.
- **Bulk install** validates every chart first and opens one MR per team;
  if any chart is refused, none is opened.
- Before an MR opens, the team repo as it would be after the change is
  linted (ADR-0023); a change that adds an error is refused.

## Alternatives rejected

- **Writing `<chart>.yaml` always**, as the legacy service did. An empty file
  is harmless, but a key it carries by habit (`targetRevision`) is not.
- **Removing a fleet default by editing `exclusions.yaml`.** It is the
  documented procedure, but rewriting the file loses its comments; deferred
  until Wingman can edit YAML preserving them.
- **Letting remove de-register the cluster.** The user asked to remove one
  chart, not the team's other charts on that cluster.

## Consequences

- Wingman never detaches a cluster from fleet upgrades without a request that
  says so in its body and a warning in its MR.
- Teardown and sync stay manual until an ArgoCD port exists.

## Verification

`apps/day2-service/tests/unit/application/test_changes.py` (exact files,
titles, branches; XOR; emergency pins; stale updates and removes conflict;
the `.gitkeep`; bulk) and `tests/api/test_api.py` (the same through HTTP).
