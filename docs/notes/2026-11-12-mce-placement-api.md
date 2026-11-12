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

Placement needs the MCE hubs (`CLUSTER_STATUS_ENABLED`, as live status and
the nodes view do). With them off, `GET /placement` answers 501
`FEATURE_DISABLED`, the form keeps its MCE select as before, and create checks
nothing new.

## 1. The rule

**Inputs**: the site, the environment (`prod` or `prep`), the OpenShift
version, the owner (the cluster's mador, ADR-0028) and the flavor. The flavor
is recorded with the decision; it does not change it.

**Candidates**: the MCE folders under `sites/<site>/mces/` whose name says
that environment, `ocp4-<env>-mce-<site>-<letter>` (ADR-0014). An MCE that
does not follow the convention is never a candidate.

**Checks** (a candidate that fails one is not offered, and says why):

| Check | Passes when | Unknown when |
|---|---|---|
| `version` | the MCE hosts the version: it is in the MCE's list from the upgrade ladder (ADR-0034) | no version was asked for yet |
| `free_pods` | at least `PLACEMENT_MIN_FREE_PODS` (default 70) free pods | the MCE could not be read |
| `readable` | Wingman read the MCE's nodes and pods | never: it passes or fails |

Free pods are counted on every Ready, schedulable node of the MCE,
control-plane (master) nodes excluded: the sum of their
`status.allocatable.pods`, less the pods on them that are not `Succeeded` or
`Failed`. A node with the `node-role.kubernetes.io/master` or
`node-role.kubernetes.io/control-plane` label is excluded even when it is
also a worker. The MCE's nodes and pods are read when the form asks (a
5-second cache, shared by everyone), never from a source minutes old.

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
  cluster of no known owner.
- *Spare servers* (server-scan's fleet rows, `GET /api/v1/servers/rows`,
  cached as for the nodes view): rows with `openshift_state ==
  "INSTALLED_TO_INVENTORY"` and `mce_name` equal to the MCE (registered to
  the MCE, in no cluster; the MCE keeps them to repair a cluster). *Usable*:
  of those, not in maintenance, reachable, not stale, health neither
  `CRITICAL` nor `UNKNOWN`, and not contested. An MCE server-scan never names
  in any row is *unknown*, never 0; so is every MCE while server-scan is not
  configured or cannot be read. server-scan's `mce_name` is matched to the
  folder name exactly.

## 2. `GET /api/day1/placement?site=&env=&version=&owner=&flavor=`

Any signed-in user.

| Parameter | Required | Rule |
|---|---|---|
| `site` | yes | a site folder; unknown: 404 `NOT_FOUND` |
| `env` | yes | `prod` or `prep` (`test`, by the naming rule, too) |
| `version` | no | an OpenShift release, `4.N.N` (a `-x86_64` suffix is dropped). Without it, every `version` check is `unknown` and there is no pick |
| `owner` | no | the mador, 1 to 10 digits; otherwise 422 `VALIDATION_ERROR`. Without it, ranking step 1 is skipped and `owner_clusters` is `null` |
| `flavor` | no | the flavor's name, echoed back |

The form calls it once with site and env to get `versions` (what the
candidates host, together), then again with the version and owner to get the
pick.

```json
{
  "site": "site1",
  "env": "prod",
  "version": "4.18.22",
  "owner": "7",
  "flavor": "agent-standard",
  "min_free_pods": 70,
  "versions": ["4.18.22", "4.17.30", "4.16.27"],
  "pick": "ocp4-prod-mce-site1-b",
  "why": "ocp4-prod-mce-site1-b has the fewest clusters of owner 7: 0, against 2 on ocp4-prod-mce-site1-a.",
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
        {"check": "version", "status": "pass", "detail": "Hosts OpenShift 4.18.22."},
        {"check": "free_pods", "status": "pass", "detail": "212 free pods; a new cluster needs 70."},
        {"check": "readable", "status": "pass", "detail": "Wingman read its nodes and pods."}
      ],
      "versions": ["4.18.22", "4.17.30", "4.16.27"],
      "clusters": 2,
      "open_creates": 1,
      "owner_clusters": 0,
      "spare": {"total": 3, "usable": 2},
      "spare_detail": null,
      "pods": {
        "free": 212,
        "allocatable": 500,
        "used": 288,
        "nodes_counted": 2,
        "nodes_excluded": {"control_plane": 3, "not_ready": 0, "unschedulable": 1}
      }
    },
    {
      "mce": "ocp4-prod-mce-site1-a",
      "eligible": true,
      "picked": false,
      "rank": 2,
      "behind_on": "owner_clusters",
      "checks": ["…all pass…"],
      "versions": ["4.18.22", "4.17.30", "4.16.27"],
      "clusters": 6,
      "open_creates": 0,
      "owner_clusters": 2,
      "spare": {"total": 3, "usable": 1},
      "spare_detail": null,
      "pods": {"free": 140, "allocatable": 750, "used": 610, "nodes_counted": 3,
               "nodes_excluded": {"control_plane": 3, "not_ready": 0, "unschedulable": 0}}
    },
    {
      "mce": "ocp4-prod-mce-site1-c",
      "eligible": false,
      "picked": false,
      "rank": null,
      "behind_on": null,
      "checks": [
        {"check": "version", "status": "fail", "detail": "Hosts 4.16 to 4.17 only (4.17.30, 4.16.27), not 4.18.22."},
        {"check": "free_pods", "status": "fail", "detail": "40 free pods; a new cluster needs 70."},
        {"check": "readable", "status": "pass", "detail": "Wingman read its nodes and pods."}
      ],
      "versions": ["4.17.30", "4.16.27"],
      "clusters": 1,
      "open_creates": 0,
      "owner_clusters": 0,
      "spare": null,
      "spare_detail": "server-scan names no server for ocp4-prod-mce-site1-c, so its spare servers are unknown.",
      "pods": {"free": 40, "allocatable": 250, "used": 210, "nodes_counted": 1,
               "nodes_excluded": {"control_plane": 3, "not_ready": 1, "unschedulable": 0}}
    }
  ]
}
```

- `candidates` are the eligible ones by `rank`, then the others by name.
- `checks[].status` is `pass`, `fail` or `unknown`; `detail` is one sentence
  in plain words. An MCE Wingman cannot read has `readable` `fail` (the
  detail says why: no token for it, its token was refused (it needs `list` on
  nodes and pods), or it did not answer) and `free_pods` `unknown`, and
  `pods` is `null`. It is never picked.
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
  below 0.

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
site, the MCE's environment, the rendered `mastertag` and the rendered
`owner.mador`, and answer:

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
has the ClusterRole; [3.9-to-3.10.md](../upgrade/3.9-to-3.10.md) has the steps.

Pods are listed in Kubernetes' Table form (`Accept:
application/json;as=Table;v=v1;g=meta.k8s.io`, `includeObject=None`), only
the ones not `Succeeded` or `Failed` (`fieldSelector`), 500 per page
(`limit`, `continue`): one short row per pod with its node, never the pod
objects.

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

`DAY1_FAKE_FLEET=true` (development) also fakes each MCE's nodes and pods
(`dev/fleet-fixtures/mce.yaml`, `hubs:`), so the form shows differing
numbers: on site1, prod, three candidates, one of them failing.
