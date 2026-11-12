# ADR-0044: A flavor's changes reach each cluster through its own MR, which the customer takes when ready; a cluster is measured against its own version

Date: 2026-11-12
Status: Accepted (supersedes in part ADR-0016, ADR-0036 and ADR-0037)

## Context

A flavor fixes values for every cluster that follows it (ADR-0026,
ADR-0036). Until now:

- an import linked every picked cluster in one MR (ADR-0037);
- drift compared every cluster with the flavor's **newest** version, so a
  flavor change made every cluster "drifted" at once;
- a cluster moved to a new version only when someone pressed Sync on its
  page.

The user's decision of 2026-11-12, first for import and then for the whole
flavor:

> "A change inside a flavor creates one MR, one for each cluster, so we can
> handle the apply and the rollout for each cluster individually. Then we
> don't have 1,000 clusters rolling at once, or 999 out of sync because of
> a change everyone needs but I can apply right now only to one customer."
> "The reason we did it is not the rollout or the import — it's to keep the
> blast radius small and let the customer decide when they're comfortable
> taking the change. This is one concept, not two features."

Asked whether to open the MRs for every cluster or let someone choose, the
user chose to open them all automatically.

## Decision

**One concept: a flavor reaches each cluster through that cluster's own
MR.** Nothing changes on a cluster until its MR merges, and each customer
merges theirs when ready. Every day1 path that changes a cluster file for a
flavor (import, a new version, a sync by hand) is one cluster per MR.

**A cluster is measured against its own version.** Drift (ADR-0036)
compares the file with the flavor as it was at the version its header
names (`# specVersion`). Missing add-ons are judged by that version's
list too.

- Old versions are read from the specs repo's history: the newest of the
  file's last 100 commits whose content names that version.
  `SpecCatalog.at_version` keeps a version once found, since a version
  never changes.
- A newer version is an **update** (`update: {version, merge_request}`),
  never drift.
- A header with no version, or a version history does not have, is
  `unknown`, never in sync.
- Saving a flavor needs a version never saved before: an edit that keeps
  the version, or reuses an earlier one, is refused (422). This is what
  makes a version a fixed point to measure against.

**A new version opens one MR per cluster, automatically.** When a flavor's
new version is on the specs repo's main, every cluster that follows it and
is on an older version gets one day1 MR. That MR is the sync to the new
version, `SyncService.plan`: the locked values and machine configs, and the
header's `specVersion`.

- **Branch:** the MR's branch names it, `platform/rollout/<flavor>/v<version>/<cluster>`
  (`mr_conventions.rollout_branch`, an addition to ADR-0007's formats).
- **Title:** a sync's title, `Sync cluster <name> to spec <flavor> v<version>`.
- **Labels and author:** labels `wingman`, `day1`, `sync`, `rollout`;
  author `system:wingman-rollout`.
- **Description:** what the MR does to that one cluster (the values it
  sets, the configs it removes, the nodepools whose nodes roll and how), and
  that closing it declines the version.

The rest of the rollout:

- **Triggers.** A rollout starts in any of these ways:
  - right after Wingman merges the flavor's MR;
  - from the specs project's webhook;
  - when an admin presses Reconcile (`POST /specs/{name}/rollout`);
  - when the rollout status is read with work pending (the fallback).

  Each trigger runs the same idempotent reconcile, in the background of the
  replica that was asked, one run per flavor at a time.
- **GitLab is the state.** A run reads the cluster headers and the open and
  closed MRs (titles, labels and branches), and opens only what is missing.
  So a rerun, a restarted replica or a second replica finds the branch or
  its MR instead of opening a duplicate. Nothing about a rollout is stored
  anywhere but GitLab; a replica keeps only its last run and its recent
  failures, for display and back-off.
- **Unconfirmed writes are not resent blindly (ADR-0006).** A cluster whose
  write GitLab did not confirm is retried by the next run only after its
  branch is checked. If the commit landed, only the MR is opened (counted as
  `recovered`). A read-triggered run waits `RETRY_AFTER` (5 minutes) before
  retrying a failed cluster; Reconcile retries at once.
- **Four at a time, and stop when GitLab stops answering**, as an import
  does. A full fleet is opened in the background, never inside one HTTP
  request: a request is cut by the proxy's 60 s, and a cut request invites a
  retry.
- **Superseded MRs.** When a cluster gets its MR for a new version, an open
  sync MR of the same cluster to an older version of the flavor is
  commented on ("Superseded by !N …") and closed. A cluster has one open
  sync MR at a time. Close-with-a-comment is chosen over replacing the old
  MR's branch: the old MR's review and history stay readable, and nothing
  force-pushes. A sync by hand supersedes the same way. It is refused (409)
  while an MR already takes the cluster to the newest version.
- **Needs a decision.** A cluster the sync cannot change without a person
  gets no MR. The cases are a nodepool whose hardware type must be chosen, a
  position the file lacks, and a file Wingman cannot edit. The rollout lists
  the cluster with the reason, and a person syncs it from its page.
- **Declined.** A rollout MR closed unmerged declines that version for that
  cluster: no new one opens. Wingman's own supersede closes only older
  versions, so it never looks like a decline.
- **Add-ons.** For add-ons the new version lists and the cluster lacks,
  day1 first asks day2 for their install MRs, which day2 opens as for any
  request.
  - Day1 asks once per team, with an admin service session
    (`system:wingman-rollout`), so a team that gave Wingman no write access
    (ADR-0043) is only its own refusal.
  - Those already open on the cluster are not asked again.
  - The day1 MR links the day2 MRs, or lists what could not be opened.
  - Day1 still never writes a day2 repo itself.
- **The one confirmation is merging the flavor MR.** Its review page
  (`GET /approvals/{iid}/rollout`) shows, before the merge:
  - how many cluster MRs will open;
  - which clusters will roll nodes, and how;
  - which lose configs;
  - which need a decision;
  - which add-ons the version adds.

  Each cluster MR then repeats what it does to that cluster.

**Import is the same engine** (the first part of this decision).

- Every pick is checked first: the flavor version, the stale check, each
  status. One refused or moved pick opens nothing.
- Then one MR per cluster, `Import cluster <name> into spec <flavor>
  v<version>`, changes only its file's header and shows only its own drift.
- MRs open four at a time; each failure is its cluster's; no more start
  once GitLab stops answering.
- `POST /specs/{name}/import` answers with `merge_requests` and `failed`
  (`docs/notes/2026-11-12-import-mr-per-cluster.md`).

The web shows a cluster's state in this order of precedence:

- drifted (against its own version);
- unknown;
- update MR open (vN → vM), linking it;
- update available;
- in sync on vN.

The flavor page shows the rollout's progress, and admins see a Reconcile
button. `docs/notes/2026-11-12-flavor-rollout-api.md` has the JSON.

## Alternatives rejected

- **One MR for many clusters** (ADR-0037's import): all or nothing for
  every cluster in it.
- **Drift against the newest version** (ADR-0036 as written): a flavor
  change makes every cluster drifted at once, though nothing on any of them
  changed.
- **Let a person choose which clusters get the update**: the user chose to
  open them all; each customer's merge is the choice.
- **Opening the MRs inside the merge request** (a 1,000-cluster fleet):
  outlasts the proxy and invites a duplicate on retry.
- **Rollout state in memory, or in a Wingman-owned file**: a restart or a
  second replica would disagree with GitLab. GitLab already holds the truth
  (headers, MRs, branches), and every file under `hostedClusters/` is an Argo
  Application (ADR-0012).
- **A timestamped branch per rollout MR**: a rerun could not tell its own
  earlier attempt from nothing, and would open a duplicate.
- **Replace an older version's MR in place** (push the new change onto its
  branch): rewrites what a reviewer may be reading. Wingman never
  force-pushes.
- **Retrying an unconfirmed write**: ADR-0006. The branch is checked first.
- **Day1 writing day2's repos for the add-ons**: day2 owns day2's repos,
  rules and lints (ADR-0016, ADR-0022). Day1 asks.

## Consequences

- A flavor change never rolls the fleet at once. Each cluster rolls when its
  customer merges, and one customer can take a fix today.
- A fleet of *n* clusters that follow a flavor gets up to *n* open MRs for
  each new version. The approvals list and the flavor's rollout panel show
  them. Closing one declines that version; a person can still sync by hand.
- After the upgrade, clusters already behind their flavor's newest version
  get their MRs at the first trigger. Clusters whose header names a version
  the history lacks (flavors edited without a new version before this rule)
  are `unknown` until synced.
- Day1 holds an admin session towards day2. It is minted from the shared
  JWT secret, as day1's viewer session was, and used only for a rollout's
  installs (ADR-0016 superseded in part).
- `ClusterProvisioner` stays `apply` alone. A rollout's MRs go through
  `RolloutMergeRequests` (a named branch, recover, supersede), because a
  workflow that replaces the provisioner (ADR-0017) would not own them.
- New metrics, with labels from fixed sets only (never a cluster, flavor or
  version), in `docs/ops/metrics.md`:
  - `wingman_rollout_runs_total{trigger}`;
  - `wingman_rollout_merge_requests_total{outcome}`.

  GitLab gains one port method, `comment_on_merge_request`, in the contract
  suite.
- No other day1 write opens one MR for several clusters. Create, modify,
  delete and sync take one cluster; a spec's MR changes only the specs repo;
  editing an MR commits only the files that MR already changes.

## Verification

- `apps/day1-service/tests/unit/application/test_rollouts.py`:
  - versioned drift: each state, an old version from history, a version
    history lacks, a header without one, add-ons per version;
  - the rollout opens one MR per cluster on its own branch, each changing
    only its file;
  - needs-a-decision gets no MR;
  - a rerun and a fresh replica open nothing;
  - an unconfirmed MR is recovered by its branch without a second commit;
  - no more MRs start once GitLab stops answering;
  - a newer version supersedes the older MR with a comment;
  - a closed MR declines the version;
  - merged MRs leave the cluster on the version;
  - day2 is asked once per cluster, and a refusing team is listed;
  - a read starts a run;
  - the approve page's preview;
  - a sync by hand is refused while an MR is open, and supersedes an older one.
- `apps/day1-service/tests/api/test_rollout_api.py`:
  - the approve trigger and the review page's counts;
  - the webhook trigger;
  - Reconcile is for admins;
  - the JSON the web reads;
  - the 409 sync and the 422 version rule.
- `apps/day1-service/tests/unit/application/test_imports.py`,
  `.../infrastructure/test_merge_requests.py`, `.../test_guards.py`,
  `apps/day1-service/tests/api/test_flavor_links_api.py`: the import, one MR
  per cluster.
- `apps/day1-service/tests/unit/infrastructure/test_day2_installs.py`,
  `apps/day2-service/tests/api/test_service_session.py`: the day2 asks, per
  team, and day2 accepting the rollout's session.
- `packages/wingman-core/tests/unit/domain/test_mr_conventions.py` (the
  rollout branch round trip), the contract suite (`comment_on_merge_request`
  on the fake and on GitLab CE), `test_metrics_catalogue.py`.
- `apps/web/e2e/tests/flavor-import.spec.ts` and the rollout and drift-state
  specs.
