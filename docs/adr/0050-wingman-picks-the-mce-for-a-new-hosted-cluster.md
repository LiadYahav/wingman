# ADR-0050: Wingman picks the MCE for a new hosted cluster, and shows why

Date: 2026-11-12
Status: Accepted; amends rule 2 of `docs/ideas/architecture-fit.md` (Wingman checks the free pods a control plane needs and ranks MCEs, and still reserves nothing)

## Context

The create form asked the person for the site and the MCE. Which MCE runs a
new cluster's control plane is the platform's concern, not the customer's:
the architecture wants it hidden ("forms that hide placement"), and the
architect decided Wingman picks it (`docs/ideas/single-pane.md`,
decisions 5 to 9, 15, 16 and 19; the user confirmed them on 2026-11-12):

- from the site, the environment (prod or prep) and the OpenShift version;
- the "customer" is the cluster's owner, its mador (ADR-0028);
- spare servers come from server-scan, and more is better, not a
  requirement;
- fewer clusters on an MCE is better, with no hard cap;
- the order is: the checks, then fewest of this owner, then fewest overall,
  then most spare;
- free pods are counted on every Ready, schedulable node, control-plane
  nodes excluded;
- an admin may choose another MCE that passes the checks, with a reason
  written into the MR next to the numbers.

cluster-navigator's figures are up to 30 minutes old and carry no free
pods (its pod figure is allocatable pods over all nodes), so two creates in
that window would see the same number. The MCE itself is the only fresh
source.

## Decision

1. **The rule is pure** (`wingman_day1.domain.placement`), and
   `PlacementService` reads its inputs. Inputs: site, env, version, owner,
   flavor. The flavor is recorded with the decision; it does not change it.
2. **Candidates** are the MCE folders at the site whose name says the env
   (`ocp4-<env>-mce-<site>-<letter>`, ADR-0014).
3. **Three required checks**, each with one sentence on why:
   - `version`: the MCE hosts it (ADR-0034's list); unknown until chosen;
   - `free_pods`: at least `PLACEMENT_MIN_FREE_PODS` (default 70);
   - `readable`: Wingman read the MCE's nodes and pods. An MCE it cannot
     read (no token, a token without the grant, no answer) fails it, its
     free pods are unknown, and it is never picked.
4. **Free pods** (`wingman_day1.domain.mce_capacity`): the sum of
   `status.allocatable.pods` over the nodes that are Ready, not
   `spec.unschedulable` and carry neither the `master` nor the
   `control-plane` role label, less the pods bound to those nodes that are not
   `Succeeded` or `Failed`, which is what the scheduler counts against a
   node's limit. A node with a control-plane role is excluded even when it is
   also a worker (decision 16 as written). Never below 0.
5. **How the pods are read.** `HubApi.pods_per_node` lists pods cluster-wide
   as `meta.k8s.io/v1` Table rows (`Accept:
   application/json;as=Table;v=v1;g=meta.k8s.io`, `includeObject=None`), only
   the non-terminal ones (`fieldSelector=status.phase!=Succeeded,status.phase!=Failed`),
   500 per page with `continue`, and counts the `Node` column. Nodes are read
   whole (`/api/v1/nodes`, also paged): the Table has no column for their
   allocatable pods, and a hub has tens of nodes, not thousands. Measured with
   `scripts/dev/bench_placement_pods.py` (synthetic pods shaped like a hosted
   control plane's; real ones are often larger):

   | Pods | Table rows | Pod objects |
   |---|---|---|
   | 3,000 (6 pages) | 0.37 MB, parsed in 0.002 s | 26.5 MB, 0.09 s |
   | 10,000 (20 pages) | 1.2 MB, 0.006 s | 88 MB, 0.30 s |

   About 122 bytes a pod against 8.8 KB. The API server compresses either
   for a client that asks (httpx does), but it still builds, and day1 still
   decodes, the full objects in the second case.
6. **Read fresh.** Placement has its own `CachedHubApi` with a 5-second TTL
   (single-flight, shared by everyone, a failure not kept), never the 10
   seconds of live status or the minutes of another source.
7. **Counts:**
   - clusters: the files under the MCE's `hostedClusters/`, plus open
     Wingman MRs that create a cluster there. An MR's title has no MCE, so
     its diff says where (`RepoReads.merge_request_diff`, cached per head
     `sha`) and its added lines give the owner. A diff GitLab has not computed
     yet is not counted, and `problems` says so;
   - this owner's clusters: those whose `owner.mador` equals the owner, as
     text;
   - spare servers: server-scan rows in `INSTALLED_TO_INVENTORY` with that
     `mce_name`; *usable* also out of maintenance, reachable, not stale,
     neither `CRITICAL` nor `UNKNOWN`, not contested. An MCE no row names is
     unknown, never 0. `mce_name` is matched to the folder name exactly;
     `PlacementService(scan_names=…)` is where a mapping goes if production's
     names differ.
8. **Ranking**, among the candidates that pass every check: fewest of this
   owner (skipped without an owner), fewest clusters, most **usable** spare
   servers (a spare that cannot be used cannot repair a cluster; the total is
   shown beside it), an unknown count after every known one, then the name.
   The response says, for each passing candidate, the first step the pick
   beats it on (`behind_on`), and one sentence on why the pick won (`why`).
9. **No reservation, no cap.** Two creates at the same moment can get the
   same pick, and both are accepted.
10. **Create checks the choice again** (preview and create), for the rendered
    `mastertag` and `owner.mador`:
    - an MCE that fails a check: 422, with each failure;
    - the pick: accepted;
    - another MCE that passes: an override, which needs `placement.reason`
      (folded to one line, at most 500 characters) or 422. Creating already
      needs an admin, so every override is an admin's;
    - the form's `placement.pick` is the request's MCE but the pick has moved:
      409 `REVISION_CONFLICT` with `details.pick`, the new pick (a stale form,
      not an override nobody meant).
11. **The record.** In merge-request mode the MR description gains an "MCE
    placement" section above the footer, whose format is unchanged (ADR-0007):
    the pick and why, or the override, the pick it overrode and the reason, the
    inputs, and a table of every candidate's numbers and checks. The reason is
    an admin's free text: it goes in a code span, so it neither formats the
    description nor mentions anyone. In workflow mode (ADR-0042) the chosen MCE
    is the workflow's `mce` as before; the workflow writes its own MR, so the
    decision and the numbers go to day1's log as the event
    `mce_placement_chosen` (both modes log it).
12. **On with the hubs.** Placement reads every candidate's hub, so it is on
    when `CLUSTER_STATUS_ENABLED` is. With the hubs off,
    `GET /api/day1/placement` answers 501 and create checks nothing new; the
    form keeps its MCE select.
13. **Metrics** (ADR-0010): `list_nodes` and `list_pods` on the `kubernetes`
    dependency, and `wingman_placement_decisions_total{decision}` with
    `picked`, `override` and `refused`, counted at create, not preview.

## Alternatives rejected

- **cluster-navigator's figures**: up to 30 minutes old, no free pods, and
  today no MCE reports to it.
- **Listing pod objects** (the PodList): 70 times the bytes for the same
  answer (above).
- **One pod list per node** (`fieldSelector=spec.nodeName=`): as many calls as
  nodes, every time, for the same rows.
- **Counting Pending pods against the node they will land on**: they are not
  bound to one yet; the scheduler does not count them either.
- **Ranking by every spare server**: a spare in maintenance, unreachable or
  contested cannot replace a failed node. The total is shown.
- **A reservation, or a cap on clusters per MCE**: the user chose a
  preference, not a cap; a reservation would be state outside Git, which
  Wingman keeps none of. The create workflow's admission step, if it is
  built, has the last word.
- **An optional placement with its own switch**: the hubs are already the
  switch, and with them on there is no reason to let a person pick an MCE
  that fails a check.
- **A machine-readable placement footer in the MR**: nothing reads it back,
  and the footer is a contract that every older MR must keep parsing.
- **Deciding in the browser**: the browser sees no hub, no server-scan and
  no open MRs.

## Consequences

- The MCE token needs `list` on `nodes` and `pods`, cluster-wide (the chart
  README's ClusterRole; `docs/upgrade/3.8-to-3.9.md`). Until it has it, that
  MCE is never picked; if no MCE of a site and env has it, nobody can create
  there. Grant first, then upgrade.
- A hub whose nodes are all control-plane nodes (a compact hub) counts no
  free pods and is never offered (decision 16 as written; an open question).
- A cluster on its way through the provision workflow's own MR is not
  counted until it is merged (ADR-0042's consequence).
- The form shows the numbers it decided on; the MR keeps them, so a reviewer
  sees why this MCE.
- A placement read costs, per candidate, two hub reads (one page of nodes,
  a page of pods per 500), cached for 5 seconds; the day1 repo reads are the
  cached ones; server-scan's rows are the nodes view's cache.

## Verification

- `apps/day1-service/tests/unit/domain/test_placement.py`: each check
  (version, free pods at and below the minimum, unreadable, no upgrade file,
  no version yet), each ranking step (owner, clusters, usable spare, unknown
  spare after a known 0, name), no owner, ranks among the passing only, the
  admission (the pick, an override with and without a reason, a failing MCE,
  no MCE that passes, a stale pick, a reason folded and cut), and the MR
  section (the pick, an override, a harmless reason).
- `tests/unit/domain/test_mce_capacity.py`: which nodes count, a compact hub,
  spare and usable servers, an MCE server-scan never names.
- `tests/unit/infrastructure/test_hub_api_capacity.py`: the Table request
  (Accept, field selector, `includeObject`, `limit`), three pages with
  `continue`, one metric per page, a list that never stops paging, anything
  but a pod Table, quantities, a 403 naming the path and never the token.
- `tests/api/test_placement_api.py`: the read with and without a version, the
  numbers and the pick on three MCEs, the setting, bad inputs, 501 without the
  hubs, an MCE whose token is refused, create on the pick and on another MCE
  (the MR's section, the metric), a failing MCE, a stale pick (409 with
  `details.pick`), an open create counted for its MCE and owner, a diff not
  ready, server-scan down, the workflow getting the chosen MCE and the log
  event.
- `scripts/dev/bench_placement_pods.py`: the sizes above.
- `apps/web/e2e/tests/mce-placement.spec.ts`: the form (the pick and why, a
  failing MCE explained, an override needing a reason, the pick changing, the
  fallback with the hubs off).
