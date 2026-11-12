# ADR-0050: Wingman picks the MCE for a new hosted cluster, and shows why

Date: 2026-11-12
Status: Accepted; amends rule 2 of `docs/ideas/architecture-fit.md` (Wingman checks the free pods a control plane needs and the servers a cluster needs, ranks MCEs, and still reserves nothing)

**The free pods rule** (the user, 2026-11-12): free = allocatable pods − pods
in use, on the worker nodes only, and it must be at least the cost of one
hosted control plane. That cost is `PLACEMENT_MIN_FREE_PODS`, default 70 (the
user's estimate is about 67 pods, not yet measured).

## Context

The create form asked the person for the site and the MCE. Which MCE runs a
new cluster's control plane is the platform's concern, not the customer's:
the architecture wants it hidden ("forms that hide placement"), and the
architect decided Wingman picks it (`docs/ideas/single-pane.md`,
decisions 5 to 9, 15, 16 and 19). The user confirmed them, and on
2026-11-12 answered the open points:

- the "customer" is the cluster's owner, its mador, which is unique on its
  own (ADR-0028);
- spare servers come from server-scan; more is better;
- fewer clusters on an MCE is better, with no hard cap;
- the order is: the checks, then fewest of this owner, then fewest overall,
  then most spare;
- **free pods are counted on the workers only.** A production MCE has three
  masters, three infra nodes (HAProxy, tainted so nothing is scheduled
  there) and its workers: "count only the workers";
- **the servers are a required check per node type**, not only a ranking
  number: "does it have enough in the inventory of the InfraEnv (the node
  type), plus healthy servers of the same type inside server-scan?";
- the flavor matters to that check (its node types and replicas), and does
  not change the ranking;
- an admin may choose another MCE that passes the checks, with a reason
  written into the MR next to the numbers.

cluster-navigator's figures are up to 30 minutes old and carry no free
pods (its pod figure is allocatable pods over all nodes), so two creates in
that window would see the same number. The MCE itself is the only fresh
source.

## Decision

1. **The rule is pure** (`wingman_day1.domain.placement`, with the counting
   in `wingman_day1.domain.mce_capacity`), and `PlacementService` reads its
   inputs: the site, the env, the version, the owner, and the flavor with its
   nodepools.
2. **Candidates** are the MCE folders at the site whose name says the env
   (`ocp4-<env>-mce-<site>-<letter>`, ADR-0014).
3. **Four required checks**, each with one sentence on why. A candidate that
   fails one is not offered; one with an unknown check is never picked.
   - `version`: the MCE hosts it (ADR-0034's list); unknown until chosen.
   - `free_pods`: the rule above.
   - `servers`: enough healthy free servers of every node type the new
     cluster needs (item 5).
   - `readable`: Wingman read the MCE's nodes and pods. An MCE it cannot read
     (no token, a token without the grant, no answer) fails it, and its free
     pods are unknown.
4. **The workers.** A node is left out of the free pods, by the first reason
   that applies, when it has the `master` or `control-plane` role label, has
   the `infra` role label, is not Ready, is cordoned (`spec.unschedulable`),
   or has a taint with the effect `NoSchedule` or `NoExecute`
   (`PreferNoSchedule` only discourages, so it does not count). A node with a
   control-plane or infra role is left out even when it is also a worker.
   Pods in use are those bound to a counted node that are not `Succeeded` or
   `Failed`, which is what the scheduler counts against a node's limit. Free
   pods are never below 0.
5. **Servers of each node type.**
   - *Needs*: per InfraEnv, the replicas of the nodepools that use it,
     summed. The form sends its nodepools (`need=<infra_env>:<replicas>`,
     ratio-sized replicas included; an empty `need=` says none). Without
     any `need`, the flavor's preset nodepools that name an InfraEnv are the
     needs. At create, the rendered file's `nodepool[]` (`infraEnvName`,
     `replicas`).
   - *Free*: the MCE's Agents in that InfraEnv (label
     `infraenvs.agent-install.openshift.io`) that the Agent provider would
     take: bound to nothing, approved, connected, validated. This is the
     nodes view's own rule (`node_pools.why_not_free`, ADR-0038).
   - *Healthy*: each free Agent is joined to its server in server-scan as the
     nodes view joins them (`node_pools.ServerFinder`: the BareMetalHost name,
     then MAC, then serial). It counts when that server is out of
     maintenance, reachable, not stale, neither `CRITICAL` nor `UNKNOWN`, and
     not contested.
   - *Per type*: enough when healthy free ≥ needed ("dell-r660: 4 healthy
     free of 3 needed"); short when fewer, and also when there are fewer free
     Agents than needed at all; unknown when the Agents or server-scan could
     not be read, or when free Agents server-scan has no server for would be
     needed to reach the count.
   - *The check*: fails when one type is short, is unknown when one is
     unknown and none is short, and passes when every type is enough. With no
     type named yet there is nothing to check, and it passes; the form then
     says the pick may change once the nodepools name their types.
   - *Without server-scan configured* (`SERVER_SCAN_URL` empty), the free
     Agents are counted as they are, and each type's sentence says their
     health was not checked. A configured server-scan that does not answer
     makes the check unknown.
6. **Read fresh.** Placement has its own `CachedHubApi` with a 5-second TTL
   (single-flight, shared by everyone, a failure not kept), never the 10
   seconds of live status or the minutes of another source.
7. **Counts for the ranking:**
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
   servers (the total is shown beside it), an unknown count after every known
   one, then the name. The response says, for each passing candidate, the
   first step the pick beats it on (`behind_on`), and one sentence on why the
   pick won (`why`).
9. **No reservation, no cap.** Two creates at the same moment can get the
   same pick, and both are accepted.
10. **Create checks the choice again** (preview and create), for the rendered
    `mastertag`, `owner.mador` and nodepools:
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
    the pick and why, or the override, the pick it overrode and the reason; the
    inputs, needs included; and a table of every candidate's numbers, its
    healthy free servers per type, and its checks. The reason is an admin's
    free text: it goes in a code span, so it neither formats the description
    nor mentions anyone. In workflow mode (ADR-0042) the chosen MCE is the
    workflow's `mce` as before; the workflow writes its own MR, so the decision
    and the numbers go to day1's log as the event `mce_placement_chosen` (both
    modes log it).
12. **On with the hubs.** Placement reads every candidate's hub, so it is on
    when `CLUSTER_STATUS_ENABLED` is. With the hubs off,
    `GET /api/day1/placement` answers 501 and create checks nothing new; the
    form keeps its MCE select.
13. **Metrics** (ADR-0010): `list_nodes` and `list_pods` on the `kubernetes`
    dependency (`list_agents` also counts the servers check's reads), and
    `wingman_placement_decisions_total{decision}` with `picked`, `override` and
    `refused`, counted at create, not preview.

## Alternatives rejected

- **cluster-navigator's figures**: up to 30 minutes old, no free pods, and
  today no MCE reports to it.
- **Counting every schedulable node, infra nodes included**: their pods are
  HAProxy's, and their taint keeps a control plane off them.
- **Listing pod objects** (the PodList): about 70 times the bytes for the
  same answer (below).
- **One pod list per node** (`fieldSelector=spec.nodeName=`): as many calls as
  nodes, every time, for the same rows.
- **Counting Pending pods against the node they will land on**: they are not
  bound to one yet; the scheduler does not count them either.
- **Spare servers as the only server figure** (a ranking number): the user
  wants the MCE to have the servers of each type the cluster asks for; a
  spare of another type does not help.
- **Free Agents without server-scan's health**: an Agent in maintenance or
  contested would be counted as a server the cluster can have.
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
  README's ClusterRole; `docs/upgrade/3.9-to-3.10.md`). Until it has it, that
  MCE is never picked; if no MCE of a site and env has it, nobody can create
  there. Grant first, then upgrade. The servers check lists `agents` across
  the hub, which the 3.4 ClusterRole already grants.
- A hub whose nodes are all masters or infra nodes counts no free pods and is
  never offered.
- The pick can change once the nodepools name their node types: before that
  the servers check has nothing to check. The InfraEnv list follows the
  chosen MCE, so a type the pick lacks takes it out, and the pick moves to an
  MCE that has it.
- A cluster on its way through the provision workflow's own MR is not
  counted until it is merged (ADR-0042's consequence).
- The form shows the numbers it decided on; the MR keeps them, so a reviewer
  sees why this MCE.

## The cost of reading

How the rule's inputs are read, and what that costs; none of this changes the
rule above.

- **Pods** are listed cluster-wide as `meta.k8s.io/v1` Table rows (`Accept:
  application/json;as=Table;v=v1;g=meta.k8s.io`, `includeObject=None`), only
  the ones not `Succeeded` or `Failed`
  (`fieldSelector=status.phase!=Succeeded,status.phase!=Failed`), 500 per
  page with `continue`, and the `Node` column is counted. Measured with
  `scripts/dev/bench_placement_pods.py` (synthetic pods shaped like a hosted
  control plane's; real ones are often larger):

  | Pods | Table rows | Pod objects |
  |---|---|---|
  | 3,000 (6 pages) | 0.37 MB, parsed in 0.002 s | 26.5 MB, 0.09 s |
  | 10,000 (20 pages) | 1.2 MB, 0.006 s | 88 MB, 0.30 s |

  About 122 bytes a pod against 8.8 KB. The API server compresses either
  for a client that asks (httpx does), but it still builds, and day1 still
  decodes, the full objects in the second case.
- **Nodes** are read whole (`/api/v1/nodes`, paged): the node Table has no
  column for their taints or allocatable pods, and a hub has tens of nodes,
  not thousands.
- **Agents** are read only when the nodepools need servers, only those of the
  needed InfraEnvs (`labelSelector=infraenvs.agent-install.openshift.io in
  (…)`), across the hub or in `MCE_INFRAENV_NAMESPACE`, paged.
- Per candidate, a placement is one page of nodes, a page of pods per 500,
  and a page of Agents per 500 of the needed types, cached for 5 seconds; the
  day1 repo's reads are the cached ones; server-scan's rows are the nodes
  view's cache.

## Verification

- `apps/day1-service/tests/unit/domain/test_placement.py`: each check
  (version, free pods at and below the minimum, the servers per type: enough,
  short, too few Agents, unknown Agents, unknown health, free Agents not in
  server-scan, a short type beating an unknown one, no server-scan, no type
  named yet; unreadable), each ranking step (owner, clusters, usable spare,
  unknown spare after a known 0, name), no owner, ranks among the passing
  only, the admission (the pick, an override with and without a reason, a
  failing MCE, no MCE that passes, a stale pick, a reason folded and cut), and
  the MR section (the pick, an override, a harmless reason, the servers per
  type).
- `tests/unit/domain/test_mce_capacity.py`: only the workers count (masters,
  infra nodes, taints, not Ready, cordoned), a compact hub, needs summed per
  type, free Agents joined to server-scan and counted when healthy, every
  per-type status, spare and usable servers, an MCE server-scan never names.
- `tests/unit/infrastructure/test_hub_api_capacity.py`: the Table request
  (Accept, field selector, `includeObject`, `limit`), three pages with
  `continue`, one metric per page, a list that never stops paging, anything
  but a pod Table, quantities, taints and the infra role, the Agents request
  (label selector, namespace, paging, a bad name never sent), a 403 naming
  the path and never the token.
- `tests/api/test_placement_api.py`: the read with and without a version, the
  numbers and the pick on three MCEs, the setting, bad inputs and bad needs,
  an empty `need=`, 501 without the hubs, an MCE whose token is refused,
  needs checked per type (enough, short, unknown), a type short on the pick,
  Agents the token may not list, no server-scan, create checking its own
  nodepools' needs, create on the pick and on another MCE (the MR's section,
  the metric), a failing MCE, a stale pick (409 with `details.pick`), an open
  create counted for its MCE and owner, a diff not ready, server-scan down,
  the workflow getting the chosen MCE and the log event.
- `tests/unit/infrastructure/test_fake_mce.py`: the demo hubs, and a node
  type short on each of two MCEs.
- `scripts/dev/bench_placement_pods.py`: the sizes above.
- `apps/web/e2e/tests/mce-placement.spec.ts`: the form (the pick and why, the
  servers per type, a failing and an unknown type, the needs sent from the
  nodepools, an override needing a reason, the pick changing, the fallback
  with the hubs off).
