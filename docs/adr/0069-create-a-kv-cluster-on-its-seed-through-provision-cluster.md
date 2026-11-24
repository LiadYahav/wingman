# ADR-0069: An admin creates a KV cluster on its seed through provision-cluster, the same as the ones before it, and sees each zone's fill order

Date: 2026-11-24
Status: Accepted

## Context

A KV cluster is a hosted cluster whose hub is its zone's seed and whose
bare-metal workers host the tenants' VMs (ADR-0067); Wingman manages it like
any hosted cluster (ADR-0067 §3), but could not create one: a tenant's create
starts from a flavor and refuses a seed as its MCE (ADR-0067 §4).

The user (2026-11-24): "I want to make create KV Cluster (it's simpler than a
flavor because it will be exactly the same)". And: "we are performing bin
packing of cluster && each mce. When [one] is being filled up and can't
contain [more] then we create another one (maybe it's the place to make it
automatically? But I am not sure. Maybe it can be a step inside the KubeVirt
workflow itself?)".

### What the platform says (kubevirt-workflows `main` `3ba0835`)

- **The file** is `sites/<site>/mces/<seed>/hostedClusters/ocp4-<lc>-kv-<site>-<zone>-<id>.yaml`
  (`docs/naming-convention.md` §1), `<lc>` the seed's lifecycle, `<id>` the
  lowest unused letter (acceptance P10: `-b` after `-a` on the same seed).
- **Acceptance P1**: "Create `ocp4-test-kv-five-az1-a` on the seed
  `ocp4-test-seed-five-az1-a`: one NodePool from the seed's `c200-mtl-az1`, 3
  replicas"; the run `provision-cluster-<file stem>` completes with its
  segment allocated, and "every NodePool's `nodeLabels` zone is `az1`, equal to
  the zone in the name".
- **The capacity policy** (`kv-capacity-controller.md` §3, AD31): `maxNodes`
  40 (a KV cluster's hard size), `standbyWorkers` 1 to 5 (a standby KV
  cluster's size), `freeCpuPercent` 15, `standbyClusters` 1. create-vm places a
  zone's VMs first fit, oldest first by the name's id letter (AD33).
- **Growth is the KV Capacity Controller's** (AD27, AD28, §5-§6; specification
  only, not built): on each seed it grows the zone's active KV cluster (the
  oldest under `maxNodes`) with update-nodepool, keeps `standbyClusters`
  standby KV clusters through provision-cluster, and promotion is implicit:
  once the active one reaches `maxNodes`, the oldest below it is the active
  one. provision-cluster waits for a person's merge, so a standby cluster
  needs one (open item O2).

### What provision-cluster accepts (team-redbull/workflows `main` `29ef001`, read only)

- `POST /workflows/cluster-lifecycle/provision-cluster?cluster=&mce=`, the
  file as an `application/yaml` body (`workflow_domains/cluster_lifecycle/router.py`).
- **`cluster`**: `hosted_cluster_stem` (`shared/cluster_names.py`): a
  lowercase DNS-1123 label of at most 24 characters after `ocp4-`. No rule on
  its kind: a `kv` name is accepted as any other.
- **`mce`**: `name_token` (lowercase letters, digits, single dashes), then
  `find_mce_dir` (`activities/cluster_lifecycle/day1_writer.py`) finds the
  folder **by name among every `sites/*/mces/`**. A seed's folder is found as
  any MCE's; the site is the folder's.
- **The file** (`cluster_values.validate_cluster_values`, judged with the
  merged value layers): `mastertag` `X.Y.Z[-arch]`, a non-empty `nodepool`
  whose `configs` are DNS-1123 names, `owner.merkaz`/`anaf`/`mador` present,
  none of `vlanId`, `dhcp_values`, `mcConfigMap`, `tuningConfigmap`,
  `AutomateAllocation`, a `clusterName` only when it matches the file name,
  and `day2.copy_to_sigs` with an environment from the name (cross-checked
  with the folder only when it is `ocp4-<env>-mce-…`, so never for a seed).
  **No zone check**: the convention's "refused when written" (§3, §6 item 10)
  is not built.
- **Its segment**: the `allocate-segment-HC-<cluster>` child reserves a /24 at
  the folder's site, as for a tenant's. day2 registration follows the value
  layers' `day2.copy_to_sigs` (the fixtures' seed lists none), then the
  console shortcut.
- A 422 is the name or the `mce` token; a missing folder, an existing file or a
  rejected file is a FAILED run read by its id; a 409 is a run already going.

## Decision

### 1. No form: Wingman fills the file (`domain/kv_create.py`, pure)

An admin picks a seed; the draft is the whole file.

| Part | From |
|---|---|
| Name | `ocp4-<lc>-kv-<site>-<zone>-<id>`, `<lc>` the seed name's lifecycle, the lowest `<id>` letter no cluster file and no open provision-cluster merge request has (as a tenant's name is taken, ADR-0042's amendment); it must follow the KV rule (`kind_names.py`) and provision-cluster's 24 characters. A seed whose name gives no lifecycle (the deployed `ocp4-seed-<site>-<zone>`) gets no name, and says so |
| Zone | The seed name's; a seed whose name gives none (`ocp4-<lc>-mce-seed-<site>-<id>`, ADR-0067's amendment) offers the zones of its bare-metal InfraEnvs, one to choose |
| mastertag | The seed's `values.yaml` default when the seed offers it (ADR-0034's ladder), else its newest offered release; any offered one may be chosen, each checked as a tenant's (`unhostable_problems`) |
| One NodePool | `infraEnvName` the zone's bare-metal pool, an InfraEnv named `<flavor>-mtl-<zone>` on the seed: read live from its hub while live status is on (a hub with no access configured reads as off; any other hub error is raised, never read around), else the InfraEnvs the seed's KV cluster files name. One is used, several are a choice, none falls back to the model's own when it is the zone's, else the draft says there is none. `replicas` 3 by default (P1), 1 to 40 (`maxNodes`). `nodeLabels` `{topology.kubernetes.io/zone: <zone>}`; `labels.allowDeletion: false` is the template's |
| The rest | Copied from a **model**, so every KV cluster is the same: the newest KV cluster (highest id letter) on the same seed, else on the same site, else any whose file parses. Its `owner`, its first NodePool's `configs` (its own network config, `nm-conf-<its clusterName>-<hw>`, given back as `{name: nm-conf, hardware: <hw>}` so it is expanded for the new cluster) and `tuningConfig`. With no model, the owner is the request's and there are no configs, and the draft says so |
| Agent labels | The deployment's excluded Agent labels, as on any agent cluster (ADR-0065) |

The file is rendered through the specs project's `cluster-template.j2` with
every check a tenant's file passes (`rendered_file.render_new_file`, now
shared with a flavor's create), and must hold each NodePool's zone as written
(`kv_zone_problems`, ADR-0067's amendment): a template that does not write
`nodeLabels` is refused. A KV cluster has no flavor, so its file has no
provenance header.

### 2. Two routes, admins only

| Route | What |
|---|---|
| `GET /api/day1/seeds/{seed}/kv-cluster-draft` | The draft: name, zone and zones, mastertag and versions, the zone's InfraEnvs and where they were read (`hub` or `files`), workers (default, max, the policy's standby range), the model, owner, path, the file and `problems`. `?zone=&infra_env=&mastertag=&workers=` choose; `?owner_*=` only with no model. Choices that do not fit are problems, with every option still listed; a folder that is no seed is 404 |
| `POST /api/day1/seeds/{seed}/kv-clusters` | Recomputes the draft from the body's choices and starts provision-cluster with `cluster=<name without ocp4->`, `mce=<seed>` and exactly the draft's file: 202 with the run, read by `GET /clusters/{name}/provision-run`. 422 with the draft's problems; 409 (`REVISION_CONFLICT`) when the next free name is no longer the `name` sent, so a person never creates a name they did not see. The orchestrator's refusals in its words (ADR-0042) |

Both are `AdminUser`: a viewer's 403 comes before anything is read and is
the same for every name, so it says nothing of which folders are seeds
(ADR-0067, ADR-0068). Never retried (ADR-0006); the start is logged with the
admin, the seed and the model. The tenant create is unchanged: it still
refuses a seed.

### 3. Seeds & KV Clusters: the Create, each zone's fill order

- **Create KV cluster** on each seed's card opens a dialog over the draft:
  the derived name, the zone (a choice when the seed's name gives none), the
  version, the InfraEnv, workers (1 to 40), the model it copies and the file
  (read only). Create shows the provision run with the tenant create's
  component (phase, merge request link), then what follows the merge: the
  vm-lifecycle-worker add-on for the new KV cluster through day2 (its
  `/clusters/<name>/addons` page: `kvCluster` the file stem, `site`,
  `vlanId`, `vmMacPrefix` `0e` + that VLAN; P1 criterion 6) and node
  bin-packing (`HighNodeUtilization`, the descheduler's compaction). The
  orchestrator is required in production and faked in development (ADR-0042's
  amendment), so the button is never disabled for it; Create waits until the
  draft has no problems, and shows them.
- **Each zone's fill order**, from what the page already reads (the list's
  `kv.workers`, ADR-0067's amendment): a seed's KV clusters whose NodePools
  name their zone are listed oldest first by id letter with their place
  (1st fills first, AD33) and workers against 40 as a bar, each one **Full**
  (40 or more), **Filling** (the oldest under 40, where create-vm places next)
  or **Next** (after it: "next in line"; Wingman cannot see VMs, so never
  "empty"). One whose NodePools miss its zone is listed apart, never in the
  order. A zone with no **Next** is warned: "when <filling> fills up,
  create-vm has nowhere to put <zone>'s VMs" (the controller's `KvccNoStandby`),
  with its Create KV cluster button pre-filled with the standby size (3, in
  the policy's 1 to 5).

### 4. Where the automatic path goes, and what Wingman does not do

Wingman creates no KV cluster by itself and runs no loop. The platform's
design puts growth in the KV Capacity Controller on each seed (AD27): it would
start provision-cluster itself for a standby KV cluster, whose merge request
then waits in Wingman's Approvals as any provision-cluster merge request does
(ADR-0042's amendment; O2), and the capacity policy file would be edited
through Wingman by merge request once its path and owner are decided (AD31,
O4). Both are future and not built here. Wingman's Create is the person's path
meanwhile, and the fallback after. Making it a step of a workflow (create-vm,
or a KubeVirt workflow) is the team's choice in team-redbull/workflows, not
Wingman's: create-vm holds a 5-minute zone lock (AD32), and a new KV cluster
takes far longer and waits for a person's merge, so a standby must exist
before it is needed.

## Alternatives rejected

- **A flavor for KV clusters**: the user's "exactly the same"; a flavor is a
  form, versions and per-cluster merge requests, and a KV cluster has nothing
  a person chooses but its zone, size and version.
- **Loosening the tenant create to accept a seed**: the tenant create's
  placement, flavor locks and env rules do not apply, and the refusal keeps a
  tenant's cluster off a seed (ADR-0067 §4).
- **Creating a standby KV cluster automatically from Wingman**: the
  controller's job (AD27), and Wingman keeps no loop; the warning and its
  button are the person's path.
- **A name the server picks at create time**: a create could then make a name
  the person never saw; the draft's name is sent back and checked.
- **Reading the InfraEnvs around a failed hub read**: that hides the hub's
  error; only a hub Wingman has no access to reads as off.

## Consequences

- An admin creates a KV cluster from its seed's card in a few clicks; the
  merge request is provision-cluster's, reviewed and merged in GitLab, and
  listed in Approvals as any.
- A KV cluster on a convention-named seed (`ocp4-<lc>-seed-<site>-<zone>-<id>`)
  is not found by the deployed create-vm, which looks in
  `ocp4-seed-<site>-<zone>/` (ADR-0067's consequence); Wingman creates it
  where the seed's folder is.
- The lowest free id letter can reuse a deleted cluster's letter, which then
  fills first (AD33 orders by letter).
- A zone with no standby is shown but not fixed: a person decides.

## Open questions (for the user and the team)

1. **A seed named `ocp4-seed-<site>-<zone>`** (the deployed shape) gives no
   lifecycle; should its KV clusters be `ocp4-prod-kv-…`, or should the seed be
   renamed first?
2. **A reused id letter** (a deleted `-a` with `-b` live) makes the new cluster
   first in the fill order: keep the lowest free letter (P10), or always the
   next after the highest?
3. **provision-cluster's zone check** (convention §6 item 10): Wingman writes
   and checks the zone; will provision-cluster or the day1 CI refuse a KV file
   without it for every writer?
4. **The model across sites**: with no KV cluster on the site, the model is
   any site's; is the owner the same everywhere (the platform team's), or a
   per-site owner the person should give?
5. **The vm-lifecycle-worker add-on**: should Wingman propose it through day2
   at the merge (its values are the file stem, site and VLAN), or does
   provision-cluster's `day2.copy_to_sigs` cover it once the seed's values
   list the sig?

## Verification

- `apps/day1-service/tests/unit/domain/test_kv_create.py`: a bare-metal
  pool's zone, the lowest free id, the KV rule and the 24 characters, the
  workers' range, the model (seed, site, any; a name off the convention has
  no letter), what a model gives, the inputs (one NodePool, the zone, the
  model's network config expanded again), the version choices.
- `apps/day1-service/tests/api/test_kv_create_api.py`: the fixtures' seed's
  draft and its exact file, choices and their problems, the hub's pools and a
  choice among several, an unreachable hub's 502, no model, a create's start
  on the seed with the draft's file and its run, a name taken since the draft
  (409), a refused create and the orchestrator's words, a template that does
  not write the zone, a viewer's 403 for every name, a Customer MCE or missing
  folder's 404, a seed whose name gives no zone.
- `apps/web/lib/kv-clusters.test.ts` (the fill order and its labels, the
  warning) and `apps/web/e2e/tests/kv-cluster-create.spec.ts` (the fill order,
  the warning's pre-filled Create, the dialog's draft, a choice, the run and
  what follows the merge).
