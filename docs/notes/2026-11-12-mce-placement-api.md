# MCE placement: the API the web reads (2026-11-12)

When someone creates a hosted cluster, Wingman picks the MCE that runs its
control plane, from the site, prod or prep, the OpenShift version and the
owner, and says why (ADR-0050, the plan's workstream 6). This note is the
contract between day1 and the create form. Two things change:

1. a new read, `GET /api/day1/placement`, gives every candidate MCE with its
   numbers, the checks it passed or failed and why, and Wingman's pick;
2. `POST /clusters/preview` and `POST /clusters` check the chosen MCE
   against the same rule, and take an optional `placement` object: the pick
   the form showed, and the reason when an admin chose another MCE.

Placement always runs (amended 2026-11-12, ADR-0050). The form never asks
for the MCE: it asks for the site, then prod or prep, then the version, and
shows the pick as soon as the three are chosen. With the MCE hubs on
(`CLUSTER_STATUS_ENABLED`) every check is made. With them off, `GET
/placement` still answers, from the day1 repo and server-scan: `live_reads` is
`false`, and `free_pods`, `servers` and `readable` are `not_checked` (they do
not block the pick; section 9).

## 1. The rule

**The free pods rule** (the user, 2026-11-12): free = allocatable pods − pods
in use, on the worker nodes only, and it must be at least the cost of one
hosted control plane. That cost is `PLACEMENT_MIN_FREE_PODS`, default 70 (the
user's estimate is about 67 pods, not yet measured).

**Inputs**: the site, the environment (`prod` or `prep`), the OpenShift
version, the owner (the cluster's mador, ADR-0028), and the flavor with its
nodepools: each nodepool's node type (its InfraEnv) and replicas. The flavor
matters only to the `servers` check (how many servers of each type the new
cluster needs); it does not change the ranking.

**Candidates**: the MCE folders under `sites/<site>/mces/` whose name says
that environment, `ocp4-<env>-mce-<site>-<letter>` (ADR-0014). An MCE that
does not follow the convention is never a candidate.

**Checks** (a candidate that fails one is not offered, and says why; one
whose check is unknown is never picked either):

| Check | Passes when | Unknown when |
|---|---|---|
| `version` | the MCE hosts the version: it is in the MCE's list from the upgrade ladder (ADR-0034) | no version was asked for yet |
| `free_pods` | at least `PLACEMENT_MIN_FREE_PODS` (default 70) free pods on its workers | the MCE could not be read |
| `servers` | for every node type the nodepools use, the MCE has at least as many healthy free servers of that type as the new cluster needs | the MCE's Agents or server-scan could not be read, or a free Agent server-scan has no server for is needed to reach the count |
| `readable` | Wingman read the MCE's nodes and pods | never: it passes or fails |

With live MCE reads off, `free_pods`, `servers` and `readable` are
`not_checked` instead (section 9).

**Which nodes are workers.** A production MCE has three masters, three
infra nodes (HAProxy, tainted so nothing is scheduled there) and its
workers; only the workers count. A node is left out, by the first reason
that applies, when it:

1. has the `node-role.kubernetes.io/master` or `node-role.kubernetes.io/control-plane` label (`control_plane`);
2. has the `node-role.kubernetes.io/infra` label (`infra`);
3. is not Ready (`not_ready`);
4. is cordoned, `spec.unschedulable` (`unschedulable`);
5. has a taint with the effect `NoSchedule` or `NoExecute` (`tainted`; `PreferNoSchedule` does not count).

A node with one of these roles is left out even when it is also a worker.
Allocatable pods are the remaining nodes' `status.allocatable.pods`; pods in
use are the pods on them that are not `Succeeded` or `Failed`. The MCE's
nodes and pods are read when the form asks (a 5-second cache, shared by
everyone), never from a source minutes old.

**Servers of each node type.** The *needs* are, per node type (InfraEnv),
the replicas of the nodepools that use it, summed. For each type, the MCE's
*free* servers are its Agents in that InfraEnv (label
`infraenvs.agent-install.openshift.io`) that the Agent provider would take:
bound to no cluster, approved, connected and validated (the rule of the nodes
view, ADR-0038). Each free Agent is joined to its server in server-scan the
way the nodes view joins them (its BareMetalHost name, then MAC, then
serial), and it is *healthy* when that server is out of maintenance,
reachable, not stale, neither `CRITICAL` nor `UNKNOWN`, and not contested.
For each type:

| Healthy free | Free not in server-scan | The type |
|---|---|---|
| at least the needs | any | passes: "dell-r660: 4 healthy free of 3 needed" |
| fewer, and fewer free Agents than the needs | any | fails: "dell-r650: 2 healthy free of 6 needed" |
| fewer, but enough if the ones not in server-scan were healthy | some | unknown |
| fewer | none | fails |
| unknown: server-scan configured but not answering | | unknown, unless there are fewer free Agents than the needs (fails) |
| not checked: server-scan not configured (`SERVER_SCAN_URL` empty) | | passes with at least the needs in free Agents, fails with fewer; the sentence says their health was not checked |
| unknown: the MCE's Agents could not be read | | unknown |

The `servers` check fails when one type fails, is unknown when one type is
unknown and none fails, and passes when every type passes. With no nodepool
naming a node type yet, there is nothing to check and it passes ("No
nodepool names a node type yet.").

**Ranking**, among the candidates that pass every check:

1. fewest clusters of this owner on the MCE (skipped when no owner is
   given);
2. fewest clusters on the MCE;
3. most usable spare servers; an MCE whose spare servers are unknown ranks
   after every MCE whose count is known;
4. the MCE's name.

The first is the pick. There is no reservation and no cap: two creates at
the same moment can get the same pick, and both are accepted.

**The counts:**

- *Clusters*: the cluster files under `sites/<site>/mces/<mce>/hostedClusters/`
  on the default branch, plus the open Wingman merge requests that create a
  cluster there (the same MRs the name suggestion counts, ADR-0040). In
  `DAY1_PROVISIONER=workflow` mode, the workflow's own open MRs are not seen
  (ADR-0042's consequence).
- *This owner's clusters*: those whose file (or open MR's file) has
  `owner.mador` equal to the owner. A file that does not parse counts as a
  cluster of no known owner. The mador is unique on its own.
- *Spare servers* (server-scan's fleet rows, `GET /api/v1/servers/rows`,
  cached as for the nodes view): rows with `openshift_state ==
  "INSTALLED_TO_INVENTORY"` and `mce_name` equal to the MCE (registered to
  the MCE, in no cluster; the MCE keeps them to repair a cluster). *Usable*:
  of those, not in maintenance, reachable, not stale, health neither
  `CRITICAL` nor `UNKNOWN`, and not contested. An MCE server-scan never names
  in any row is *unknown*, never 0; so is every MCE while server-scan is not
  configured or cannot be read. server-scan's `mce_name` is matched to the
  folder name exactly.

## 2. `GET /api/day1/placement?site=&env=&version=&owner=&flavor=&need=`

Any signed-in user.

| Parameter | Required | Rule |
|---|---|---|
| `site` | yes | a site folder; unknown: 404 `NOT_FOUND` |
| `env` | yes | `prod` or `prep` (`test`, by the naming rule, too) |
| `version` | no | an OpenShift release, `4.N.N` (a `-x86_64` suffix is dropped). Without it, every `version` check is `unknown` and there is no pick |
| `owner` | no | the mador, 1 to 10 digits; otherwise 422 `VALIDATION_ERROR`. Without it, ranking step 1 is skipped and `owner_clusters` is `null` |
| `flavor` | no | the flavor's name, echoed back; without `need`, its preset nodepools that name an InfraEnv are the needs. An unknown flavor is 404 |
| `need` | no, repeated | `<infra_env>:<replicas>`, one per nodepool the form has with an InfraEnv and replicas (`need=dell-r660-site1:3&need=dell-r660-site1:2&need=hp-gen11-site1:2`); the same type is summed. An empty `need=` says no nodepool names a type yet (the flavor's presets are not used). An InfraEnv that is not a DNS label, or replicas outside 1 to 1000, is 422 |

The form calls it once with site and env to get `versions` (what the
candidates host, together), then again with the version, owner and needs to
get the pick, and again whenever a nodepool's InfraEnv or replicas change.

```json
{
  "site": "site1",
  "env": "prod",
  "version": "4.18.56",
  "owner": "7",
  "flavor": "agent-standard",
  "min_free_pods": 70,
  "needs": [
    {"infra_env": "dell-r660-site1-128c-1024gb-5tb", "replicas": 3},
    {"infra_env": "hp-gen11-site1-64c-512gb", "replicas": 2}
  ],
  "versions": ["4.18.56", "4.17.58", "4.16.55"],
  "pick": "ocp4-prod-mce-site1-b",
  "why": "ocp4-prod-mce-site1-b has the fewest clusters of owner 7: 0, against 1 on ocp4-prod-mce-site1-a.",
  "problems": [],
  "server_scan_error": null,
  "candidates": [
    {
      "mce": "ocp4-prod-mce-site1-b",
      "eligible": true,
      "picked": true,
      "rank": 1,
      "behind_on": null,
      "checks": [
        {"check": "version", "status": "pass", "detail": "Hosts OpenShift 4.18.56."},
        {"check": "free_pods", "status": "pass", "detail": "400 free pods; a new cluster needs 70."},
        {"check": "servers", "status": "pass", "detail": "dell-r660-site1-128c-1024gb-5tb: 4 healthy free of 3 needed; hp-gen11-site1-64c-512gb: 2 healthy free of 2 needed."},
        {"check": "readable", "status": "pass", "detail": "Wingman read its nodes and pods."}
      ],
      "node_types": [
        {"infra_env": "dell-r660-site1-128c-1024gb-5tb", "needed": 3, "free_agents": 4, "healthy": 4,
         "not_in_server_scan": 0, "health_checked": true, "status": "pass",
         "detail": "dell-r660-site1-128c-1024gb-5tb: 4 healthy free of 3 needed"},
        {"infra_env": "hp-gen11-site1-64c-512gb", "needed": 2, "free_agents": 3, "healthy": 2,
         "not_in_server_scan": 0, "health_checked": true, "status": "pass",
         "detail": "hp-gen11-site1-64c-512gb: 2 healthy free of 2 needed"}
      ],
      "versions": ["4.18.56", "4.17.58", "4.16.55"],
      "clusters": 0,
      "open_creates": 0,
      "owner_clusters": 0,
      "spare": {"total": 2, "usable": 1},
      "spare_detail": null,
      "pods": {
        "free": 400,
        "allocatable": 500,
        "used": 100,
        "nodes_counted": 2,
        "nodes_excluded": {"control_plane": 3, "infra": 3, "not_ready": 0, "unschedulable": 1, "tainted": 0}
      }
    },
    {
      "mce": "ocp4-prod-mce-site1-c",
      "eligible": false,
      "picked": false,
      "rank": null,
      "behind_on": null,
      "checks": [
        {"check": "version", "status": "fail", "detail": "Does not host OpenShift 4.18.56; it hosts 4.17.58, 4.16.55."},
        {"check": "free_pods", "status": "fail", "detail": "40 free pods; a new cluster needs 70."},
        {"check": "servers", "status": "fail", "detail": "dell-r660-site1-128c-1024gb-5tb: 1 healthy free of 3 needed; hp-gen11-site1-64c-512gb: 0 healthy free of 2 needed."},
        {"check": "readable", "status": "pass", "detail": "Wingman read its nodes and pods."}
      ],
      "node_types": ["…"],
      "versions": ["4.17.58", "4.16.55"],
      "clusters": 0,
      "open_creates": 0,
      "owner_clusters": 0,
      "spare": null,
      "spare_detail": "server-scan names no server for ocp4-prod-mce-site1-c, so its spare servers are unknown.",
      "pods": {"free": 40, "allocatable": 250, "used": 210, "nodes_counted": 1,
               "nodes_excluded": {"control_plane": 3, "infra": 0, "not_ready": 1, "unschedulable": 0, "tainted": 0}}
    }
  ]
}
```

- `candidates` are the eligible ones by `rank`, then the others by name.
- `checks` are always the four, in this order: `version`, `free_pods`,
  `servers`, `readable`. `status` is `pass`, `fail` or `unknown`; `detail` is
  one sentence in plain words. An MCE Wingman cannot read has `readable`
  `fail` (the detail says why: no token for it, its token was refused (it
  needs `list` on nodes and pods), or it did not answer) and `free_pods`
  `unknown`, and `pods` is `null`. It is never picked.
- `needs` (top level) are the summed needs the `servers` check used, sorted
  by InfraEnv; empty when no nodepool names a type yet.
- `node_types`, per candidate, one entry per need: `free_agents` is `null`
  when the MCE's Agents could not be read; `healthy` is `null` when
  server-scan could not be read or is not configured; `health_checked` is
  `false` when it is not configured; `not_in_server_scan` counts the free
  Agents server-scan has no server for; `status` and `detail` are that type's
  part of the `servers` check.
- `eligible` is "every check passes". `rank` is 1-based among the eligible,
  `null` for the rest. `picked` is `rank == 1`.
- `behind_on`, for an eligible candidate that is not the pick: the first
  ranking step where the pick beats it, `owner_clusters`, `clusters`,
  `spare_servers` or `name`.
- `why` is one sentence on why the pick won, against the runner-up (or "the
  only MCE that passes every check"); `null` without a pick.
- `pick` is `null` when no candidate passes. `problems` then says why in
  plain words: "No prod MCE at site1 passes every check.", "site1 has no
  prod MCE (ocp4-prod-mce-site1-<letter>).", "Choose an OpenShift version.".
- `versions` (top level) is every version some candidate hosts, newest
  first; each candidate's own list is in its `versions`. A candidate without
  an `upgrade/mces/<mce>.yaml` hosts none, and its `version` check says so.
- `owner_clusters` is `null` without an owner. `spare` is `null` when the
  spare servers are unknown, with `spare_detail` saying why;
  `server_scan_error` says why for every MCE at once (not configured, or not
  answering).
- `pods.used` is the pods counted against the counted nodes. `free` is never
  below 0. `nodes_excluded` counts each left-out node once, by the first
  reason in the list above.

## 3. Create and preview check the chosen MCE

`CreateClusterIn` gains an optional `placement`:

```json
{
  "name": "ocp4-prod-rcs-site1-a",
  "site": "site1",
  "mce": "ocp4-prod-mce-site1-a",
  "spec_name": "rcs",
  "spec_version": "1.2.0",
  "variables": {"owner_mador": "7", "openshift_release_version": "4.18.22"},
  "placement": {
    "pick": "ocp4-prod-mce-site1-b",
    "reason": "Moving owner 7's clusters next to their storage on site1-a"
  }
}
```

- `pick`: the MCE Wingman picked when the form showed the placement.
- `reason`: why an admin chose `mce` instead of the pick; 1 to 500
  characters, required only then. Line breaks are folded to spaces.

With placement on, preview and create run the rule again for the request's
site, the MCE's environment, the rendered `mastertag`, the rendered
`owner.mador`, and the needs of the rendered `nodepool[]` (each entry's
`infraEnvName` and `replicas`, summed per InfraEnv), and answer:

| Case | Answer |
|---|---|
| `mce` is the pick | as before (a `reason` is ignored) |
| `mce` fails a check | 422 `VALIDATION_ERROR`: "MCE X cannot take this cluster", each failed check in `details.problems` |
| no candidate passes | 422 `VALIDATION_ERROR`: "No prod MCE at site1 can take this cluster", every candidate's failures in `details.problems` |
| `mce` passes but is not the pick, without a `reason` | 422 `VALIDATION_ERROR`: "Choosing X over Wingman's pick Y needs a reason" |
| `mce` passes, is not the pick, with a `reason` | accepted: an override, recorded |
| `placement.pick` is `mce`, but Wingman now picks another | 409 `REVISION_CONFLICT`: "Wingman's pick changed from X to Y since the form showed it: …", with `details.pick` = Y. Review the placement again |

Creating needs an admin, as before, so every override is an admin's.

**The merge request** (`DAY1_PROVISIONER=merge-request`) gets an "MCE
placement" section in its description, above the footer (whose format is
unchanged, ADR-0007): the pick and why, or the chosen MCE, the pick it
overrode and the reason; the inputs; and a table of every candidate's
numbers and checks.

**The provision workflow** (`DAY1_PROVISIONER=workflow`) gets the chosen MCE
as its `mce`, as before. The workflow writes its own merge request, so the
numbers go to day1's log as the event `mce_placement_chosen`.

The InfraEnv list (`GET /mces/{mce}/infraenvs`) and the name suggestion
(`GET /clusters/name-suggestion?site=&mce=&flavor=`) are unchanged: the form
asks them for the chosen MCE.

## 4. The MCE token's new reads

Free pods need cluster-wide `list` on `nodes` and `pods` (core API group) on
every MCE that has a token. Without the grant, that MCE's `readable` check
fails with "the MCE refused Wingman's token (403) on GET /api/v1/nodes": it
is never picked, and no other MCE is affected. The chart README's
[Live cluster status](../../deploy/helm/wingman/README.md#live-cluster-status-mce-hubs)
has the ClusterRole; [3.10-to-3.11.md](../upgrade/3.10-to-3.11.md) has the steps.

The `servers` check lists the hub's Agents of the needed InfraEnvs, across
the hub or in `MCE_INFRAENV_NAMESPACE` when it is set. The 3.4 ClusterRole
already grants `list` on `agents` cluster-wide; nothing more is needed for
it. How each read is made is in section 8.

## 5. Per-MCE API address (ADR-0045)

The tokens Secret (`MCE_TOKENS_FILE`) may give an MCE its API address
beside its token:

```yaml
ocp4-prod-mce-site1-a: <token>                     # https://api.<mce>.<MCE_API_DOMAIN>:6443
ocp4-prod-mce-site1-b:
  token: <token>
  url: https://api.hub-b.example:6443               # this MCE's own address
```

The plain form keeps working. A `url` must be `https://host[:port]`, with no
path. It is used by everything that reads the MCE: live status, InfraEnvs,
the nodes view and placement.

## 6. Metrics

- `wingman_dependency_requests_total{dependency="kubernetes"}` gains the
  operations `list_nodes` and `list_pods` (one per page).
- `wingman_placement_decisions_total{decision}` counts each create that
  passed the placement check: `picked` (Wingman's pick) or `override` (an
  admin's other choice); and each one refused: `refused`.

## 7. Demo

`DAY1_FAKE_FLEET=true` (development) also fakes each MCE's nodes, pods and
free Agents (`dev/fleet-fixtures/mce.yaml`, `hubs:`), so the form shows
differing numbers: on site1, prod, three candidates. `-c` fails (its version
and free pods). Before the nodepools name a type, the pick is `-b`; two
`dell-r650-site1-96c-768gb` move it to `-a` (`-b` is one healthy Dell short,
the other is in maintenance), and two `hp-gen12-site1-64c-512gb` keep `-b`
(`-a` is one short).

## 8. The cost of reading

How the rule's inputs are read; none of this changes the rule.

- **Pods**: Kubernetes' Table form (`Accept:
  application/json;as=Table;v=v1;g=meta.k8s.io`, `includeObject=None`), only
  the ones not `Succeeded` or `Failed` (`fieldSelector`), 500 per page
  (`limit`, `continue`): one short row per pod with its node, never the pod
  objects. About 122 bytes a pod against 8.8 KB for the objects (ADR-0050,
  "The cost of reading", measured with `scripts/dev/bench_placement_pods.py`).
- **Nodes**: read whole (their taints and allocatable pods), paged the same
  way; a hub has tens of nodes.
- **Agents**: only when the nodepools need servers, only the needed
  InfraEnvs' (`labelSelector=infraenvs.agent-install.openshift.io in (…)`),
  paged.
- Every hub read is cached for 5 seconds and shared; server-scan's rows are
  the nodes view's cache.

## 9. Without live MCE reads (amended 2026-11-12)

With `CLUSTER_STATUS_ENABLED` off (no hub, as on the sandbox), placement
still answers, from what Wingman has: the version each MCE hosts, clusters
per MCE with open create MRs, this owner's clusters, and spare servers from
server-scan when it is configured.

```json
{
  "live_reads": false,
  "pick": "ocp4-prod-mce-site1-b",
  "candidates": [
    {
      "mce": "ocp4-prod-mce-site1-b",
      "eligible": true,
      "checks": [
        {"check": "version", "status": "pass", "detail": "Hosts OpenShift 4.18.56."},
        {"check": "free_pods", "status": "not_checked", "detail": "Not checked: live MCE reads are off (CLUSTER_STATUS_ENABLED=false)."},
        {"check": "servers", "status": "not_checked", "detail": "Not checked: live MCE reads are off (CLUSTER_STATUS_ENABLED=false)."},
        {"check": "readable", "status": "not_checked", "detail": "Not checked: live MCE reads are off (CLUSTER_STATUS_ENABLED=false)."}
      ],
      "node_types": [],
      "pods": null
    }
  ]
}
```

- `not_checked` is not `unknown`: it does not block. `eligible` is "every
  check passes or is `not_checked`", so the version alone can take an MCE out.
- `pods` is `null` and `node_types` is empty; the top-level `needs` still
  echo what was asked.
- The form shows the pick and says the free pods and servers were not
  checked because live MCE reads are off. The MR description says so too, and
  its free pods and servers columns read "not checked".
- Create validates the same way: the version, an override's reason, a stale
  pick (409). With live reads on nothing changes: an MCE Wingman cannot read
  is `unknown` and never picked.
