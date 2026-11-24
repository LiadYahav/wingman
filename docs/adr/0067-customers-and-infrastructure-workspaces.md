# ADR-0067: Two workspaces, Customers and Infrastructure: seeds and KV clusters are kinds of their own, and a viewer never knows of them or of the MCEs

Date: 2026-11-23
Status: Accepted; amended by ADR-0068 (a viewer reads no MCE, no infrastructure name and no infrastructure file anywhere, and a tenant's cluster says its site but not its MCE); amended 2026-11-24 (a seed named `ocp4-<lc>-mce-seed-<site>-<id>`; see the amendments)

## Context

The platform's naming convention (`Idan-Maimon/kubevirt-workflows`
`docs/naming-convention.md` §1, read at `3ba0835`) reserves three cluster
flavors so that day1 tells an infrastructure cluster from a tenant's by its
name: `mce` (a Customer MCE, `ocp4-<lc>-mce-<site>-<id>`), `seed`
(`ocp4-<lc>-seed-<site>-<zone>-<id>`, an MCE-level folder of day1 that hosts
one zone's KV clusters) and `kv` (`ocp4-<lc>-kv-<site>-<zone>-<id>`, a
hosted-cluster file inside a seed's folder, whose bare-metal workers run the
tenants' VM workers). Every other cluster file is a tenant's hosted cluster.

Before this, Wingman read a seed as an off-convention MCE and a KV cluster as
an off-convention tenant cluster
([the readiness review](../ideas/kubevirt-seed-kv-readiness.md) §1). Every
signed-in user read the MCE lists, placement and Inventory Management
(ADR-0057), and could open any cluster.

The user (2026-11-23): "KV cluster and MCE seed and MCEs they are for admins
only no viewer should know. In addition to inventory management — Herzi keep
the place of the customers and filling their request." About KV clusters:
"it's HostedCluster for everything. I do want to manage it." And about the
top bar, which linked out to segments-manager and server-scan (ADR-0066):
"The top bar replace the server scanner and ss with them please. I meaning
like split the current where they are at both tabs."

### What the deployed workflows read

team-redbull/workflows `main` (`29ef001`, 2026-11-22) does not follow the
convention yet. `shared/cluster_names.py` names a seed
`ocp4-seed-<site>-<zone>` (`seed_cluster`) and a KV cluster
`ocp4-kubevirt-<site>-<zone>…` (`kv_cluster_prefix`, `is_kv_cluster_of`), and
`activities/vm_lifecycle/day1_repo.py` (create-vm's `list_kv_clusters`) takes
**every file** in `sites/<site>/mces/ocp4-seed-<site>-<zone>/hostedClusters/`
as a KV cluster: the folder is its filter, not `platform: kubevirt`. Its
redesign (workflows PR #26) names a seed `ocp4-<lc>-seed-<site>-<id>`, without
the zone. So a seed folder named by the convention is one create-vm does not
find today.

## Decision

### 1. Kinds, classified once

`wingman_core.domain.cluster_kinds` holds the rule, in core so day1 and day2
classify the same tree the same way:

| Kind | Recognised by |
|---|---|
| Seed (`MceKind.SEED`) | An MCE-level folder whose name carries the reserved word: `ocp4-<lc>-seed-…` (the convention) or `ocp4-seed-…` (the deployed workflows) |
| Customer MCE (`MceKind.MCE`) | Every other MCE-level folder, whatever its name (`ocp4-mce-workflow-test` included) |
| KV cluster (`HostedClusterKind.KV`) | Every cluster file in a seed's folder (as create-vm lists them), and any file named `ocp4-[<lc>-]kv-…` or `ocp4-kubevirt-…` wherever it is |
| Tenant hosted cluster (`HostedClusterKind.TENANT`) | Every other cluster file (`ocp4-<lc>-kubevirt-…` included: `kubevirt` is not reserved) |

`<lc>` is `prod`, `prep` or `test`. Only the reserved word decides the kind;
whether the rest of the name follows the convention is the naming rules'.
day1's `domain/kind_names.py` reads a seed against
`ocp4-<lc>-seed-<site>-<zone>-<id>` and a KV cluster against
`ocp4-<lc>-kv-<site>-<zone>-<id>`, matched against the site folder as every
name is (ADR-0014); the deployed shapes are read too, with their zone, and
flagged as not the convention's, as every off-convention name is. A Customer
MCE and a tenant's cluster keep their rules (`domain/names.py`). So the
convention's seeds and KV clusters are no longer flagged.

`ClusterRef.kind` is a cluster file's kind and `MceView.kind` a folder's. The
API carries them:

- `GET /api/day1/clusters` and `GET /api/day1/clusters/{name}`: `kind`,
  `"tenant"` or `"kv"`, and `naming.zone` (a KV cluster's zone);
- `GET /api/day1/mces`: `kind`, `"mce"` or `"seed"`, and `zone` (a seed's);
  a seed's `cluster_count` is its KV clusters.

### 2. What a viewer never knows

Enforced in day1 and day2, before anything is read for the request; the web
only follows (as ADR-0038's 2026-11-23 amendment did for nodes). A tenant's
cluster still says its site and MCE: that is where it lives, and how its
live status is read (superseded by ADR-0068: it says its site, never its
MCE, and is found by its name).

| Route | A viewer |
|---|---|
| `GET /api/day1/sites`, `/sites/{site}/mces`, `/mces`, `/mces/{mce}/openshift-versions`, `/mces/{mce}/infraenvs` | `AdminUser`: `403 FORBIDDEN` |
| `GET /api/day1/placement` | `AdminUser` (its answer is a list of MCEs) |
| `GET /api/day1/inventory`, `/inventory/runs`, `/inventory/mces/{mce}/infra-envs/{infra_env}/candidates` | `AdminUser` (ADR-0057's 2026-11-23 amendment) |
| `GET /api/day1/clusters`, `/clusters/drift-summary` | No KV cluster in the list |
| `POST /api/day1/clusters/bulk-status` | A KV cluster asked for is left out of the answer |
| Every `GET /api/day1/clusters/{name}…` (the file, YAML, history, drift, network, scale, scale-run, upgrade-run, excluded-agent-labels, delete-workflow), `/status`, `/status/stream`, `/provision-run` | A KV cluster, or a cluster named under a seed, is `404 NOT_FOUND` with a missing cluster's words |
| `GET /api/day1/upgrades` | No KV cluster's run |
| `GET /api/day1/specs/{name}/clusters`, `/drift`, `/rollout` | No KV cluster |
| `GET /api/day1/approvals`, `/audit/merge-requests` | No day1 merge request about a KV cluster (by the cluster its title, footer or provision branch names, and where the tree has it) |
| `GET /api/day1/approvals/{iid}` | `404` for one about a KV cluster, or whose diff touches a KV cluster's file |
| `GET /api/day2/clusters` | No `mce` destination (Customer MCEs and seeds) and no KV cluster |
| `GET /api/day2/clusters/{cluster}`, `/addons`, `/addons/{team}/{addon}`, `/history`, `/upgrade-check`, `POST /api/day2/merge-preview` | An MCE hub or a KV cluster is `404`, as an unknown destination |

The rules are `domain/visibility.py` (day1: `sees_cluster`, `require_seen`,
`seen`) and day2's `domain/visibility.py` (`sees_destination`, applied by
`Topology.visible_to`); day1's routes find their cluster through
`api/v1/visible.py`'s `cluster_ref`.

### 3. A KV cluster is managed like any hosted cluster

Edit, Scale, uninstall a node, upgrade, sync and the excluded-labels merge
request stay an admin's, as for a tenant's: the readiness review's item 2
("take a tenant's actions away") is not done, by the user's decision. Only
**Delete** differs: `DELETE /api/day1/clusters/{name}` of a KV cluster needs
the cluster's name typed in, `confirm=<name>`, and answers `422
VALIDATION_ERROR` without it; the merge request says the tenants' VM workers
it hosts are deleted with it (`domain/cluster_delete.py`). A tenant's delete
needs no name.

### 4. Placement never offers a seed, by its kind

ADR-0050's candidates are the site's Customer MCEs (`mce_kind`) whose name
gives the env; before, a seed was left out only because its name gives no
env. A create whose MCE is a seed is refused by its kind ("… is a seed: it
hosts KV clusters, never a tenant's cluster"), with placement's admission.

### 5. Two workspaces in the web

The web has two workspaces, each a sidebar of its own; the top bar is the
switch between them, for admins.

| Workspace | Who | Sidebar | Why there |
|---|---|---|---|
| **Customers** (`/`) | Everyone; a viewer has nothing else and no switch | Platform: Dashboard, Clusters, Flavors, Addons. Governance: Approvals, Audit, Lints. Help: Documentation, Settings | The tenants' side: their hosted clusters, the flavors they are made from, the add-ons on them, and the changes to all three |
| **Infrastructure** (`/infrastructure`) | Admins | Infrastructure: Overview, Customer MCEs (`/mces`), Seeds & KV Clusters (`/seeds`), Inventory Management (`/inventory`). Tools: Quick Links, then Segments Manager and Server Scan, each its own UI in a new tab. Help: Documentation, Settings | What serves the tenants: the hubs, the seeds and the KV clusters that host their VMs, the servers herzi draws from, and the links to the systems the team keeps apart |

- **The top bar** (`WorkspaceSwitch`) is a two-segment switch, Customers and
  Infrastructure, each going to its workspace's home, the one you are in
  marked (`aria-current="true"`). It is drawn for admins only. The links to
  segments-manager's and server-scan's own UIs left it for Infrastructure's
  sidebar (`GET /api/day1/platforms`, unchanged); a node's server still opens
  its page in server-scan (ADR-0066).
- **Where a page belongs** is `lib/workspaces.ts`'s `workspaceOf`: the
  Infrastructure routes by path; one cluster's pages by its kind once read (a
  KV cluster's are Infrastructure's, a tenant's Customers'), the workspace
  before until then; Help's pages keep the workspace you came from. Every
  cluster keeps its one page, `/clusters/<name>` (one view per thing): a KV
  cluster's goes back to Seeds & KV Clusters, wears a "KV cluster · zone"
  badge, names its folder a seed, and its Delete asks for its name.
- **The Customers lists count tenants only**: the Clusters list and the
  Dashboard's numbers, health, drift and versions leave an admin's KV
  clusters out (`tenantClusters`); a viewer never receives one.
- **The Dashboard's two cards that name MCEs move**: Where Clusters Run (the
  tenants' clusters by site and Customer MCE) and Free Servers (each MCE's
  free Agents, each MCE opening its servers in Inventory Management since
  2026-11-24) are the Infrastructure Overview's, under its numbers: Customer
  MCEs and their sites, seeds and their zones, KV clusters, free servers. The
  Customers Dashboard keeps its numbers, Cluster Health, Pending Approvals and
  OpenShift Versions.
- **Customer MCEs** lists each site's Customer MCEs from `GET /api/day1/mces`
  (env, hub version, cluster count, an off-convention name and stray files
  marked), each row opening its servers in Inventory Management
  (`/inventory?mce=<name>`); its Create MCE is a preview that writes nothing
  (ADR-0018's 2026-11-24 amendment). The default mastertag is the create
  form's, not the list's (2026-11-24, the user). **Seeds & KV Clusters** lists each site's seeds
  with their zone and hub version, and under each its KV clusters with their
  mastertag and live phase, each opening the cluster page; a KV-named cluster
  outside a seed is listed apart, since create-vm never finds it there.
- **Inventory Management and Quick Links** keep their routes and move to
  Infrastructure. An Infrastructure page opened by a viewer says it is an
  admin's (`AdminsOnly`) and reads nothing; Quick Links keeps its own answer
  to day1's 403.

### 6. Fixtures

`dev/gitlab-fixtures` has a seed, `sites/site1/mces/ocp4-prod-seed-site1-az1-a/`
(its `values.yaml`, `version.yaml` and `upgrade/mces/` rule) with two KV
cluster files, `ocp4-prod-kv-site1-az1-a` and `-b`; the fake fleet has its hub
(roomy, with a free-looking InfraEnv, so placement passing it over is by kind)
and `-a`'s two hypervisors, so its Nodes tab, Scale and uninstall show
locally. The existing fixtures keep their names.

## Alternatives rejected

- **Keep one sidebar, with admin-only entries**: the Infrastructure entries
  would sit among the tenants' and the top bar would still link out; the user
  asked for the top bar to split the two sides.
- **A page of its own for a KV cluster** (`/seeds/<name>`): a second view of
  one thing; the cluster page already manages a hosted cluster, and its
  workspace follows the cluster's kind.
- **Move Inventory Management and Quick Links under `/infrastructure/...`**:
  every bookmark, e2e spec and doc names `/inventory` and `/quick-links`; the
  workspace is the sidebar's, not the URL's.

- **Hide them in the web only**: a viewer's token reads the API; the user
  said no viewer should know, so the services say it.
- **Answer a viewer's KV cluster with 403**: that says it exists. A missing
  cluster's 404 says nothing.
- **Take a tenant's actions away from a KV cluster** (the readiness review's
  item 2): the user manages KV clusters as hosted clusters; only Delete takes
  other tenants' VMs with it, so only Delete asks more.
- **Recognise only the convention's names**: the deployed workflows still
  read `ocp4-seed-<site>-<zone>`; a seed named so would be a viewer's MCE.
- **Classify by `platform: kubevirt`**: that key is a cluster whose nodes are
  VMs (HyperShift's KubeVirt provider, the readiness review §2), not a KV
  cluster; the deployed workflows filter by the folder too.

## Consequences

- An admin switches workspaces from the top bar; the links out to
  segments-manager and server-scan are one click further, in Infrastructure's
  sidebar. A viewer's screens are the Customers workspace, without Inventory
  Management.

- A viewer loses Inventory Management, the MCE lists and placement, and no
  longer sees the seed's KV clusters anywhere; an admin sees what they saw,
  with each MCE's and cluster's kind.
- A seed folder must be named so create-vm finds it: today
  `ocp4-seed-<site>-<zone>`, by the convention
  `ocp4-<lc>-seed-<site>-<zone>-<id>`. Wingman recognises both; the mismatch
  is the workflows' to close (the session notes keep it).
- The approvals, the audit and the cluster lists of a viewer may be shorter
  than a page: a paged read is filtered after it is read.
- Not filtered: the audit's commit list and a commit's diff (free text and
  paths, never parsed), the lints, day2's approvals and audit, and an
  add-on's per-MCE values on its page. A viewer reading them may see an MCE's
  or a KV cluster's name; each is a later change if the team wants it.
  (ADR-0068 filters every one of them, and the others its audit found.)

## Verification

- `packages/wingman-core/tests/unit/domain/test_cluster_kinds.py`: both
  shapes of a seed and a KV cluster, the folder rule, the words that are not
  reserved.
- `apps/day1-service/tests/unit/domain/test_kind_names.py`: the convention's
  names follow it with their zone, the deployed ones are flagged with theirs;
  only a KV cluster's delete asks for its name.
- `apps/day1-service/tests/api/test_cluster_kinds_api.py`: an admin's kinds
  and the seed's zone; a viewer's lists without a KV cluster, a KV cluster's
  page as a missing one's, the bulk status, the 403s, the merge requests; the
  KV delete's name; placement never offering the seed and refusing a create
  on it.
- `apps/day2-service/tests/api/test_visibility_api.py`: a viewer's
  destinations without an MCE or a KV cluster, and naming one is a 404.
- `apps/day1-service/tests/api/test_inventory_api.py`: a viewer's 403 on
  every Inventory read.
- `apps/web/lib/workspaces.test.ts` (where each page belongs, a cluster's by
  its kind, Help's keeping the last), `lib/infrastructure.test.ts` (the
  groups and counts) and `lib/platforms.test.ts` (the links out).
- `apps/web/e2e/tests/workspaces.spec.ts`: the switch and both sidebars,
  Customer MCEs, Seeds & KV Clusters, a KV cluster's page in Infrastructure and
  its Delete's name, the Clusters list without it, a viewer's sidebar and the
  admins-only pages; `overview.spec.ts` (both Overviews) and
  `platforms-apart.spec.ts` (the links out in Infrastructure's sidebar).

## Amendment (2026-11-24): a seed named `ocp4-<lc>-mce-seed-<site>-<id>`

**A folder named `ocp4-<lc>-mce-seed-<site>-<id>` is a seed, flagged
off-convention, with its lifecycle and id read and no zone.**

The user thinks seeds may be named like `ocp4-prod-mce-seed-five-a`. No
written source gives that shape: the convention says
`ocp4-<lc>-seed-<site>-<zone>-<id>`, the deployed workflows
`ocp4-seed-<site>-<zone>`, workflows PR #26 `ocp4-<lc>-seed-<site>-<id>`.
Read as a Customer MCE, such a folder would be a viewer's MCE and a
placement candidate for a tenant's cluster, which a seed never is.

1. **The kind** (`wingman_core.domain.cluster_kinds`, so day1 and day2 agree):
   `ocp4-<lc>-mce-seed-` followed by at least two segments is a seed. So
   `ocp4-prod-mce-seed-five-a` and `ocp4-test-mce-seed-bat-yam-b` are seeds,
   and every file in them a KV cluster; `ocp4-prod-mce-seed-a` (a Customer
   MCE of the site `seed`) and `ocp4-mce-seed-five-a` (no lifecycle) are
   still Customer MCEs.
2. **The name** (day1's `domain/kind_names.py`): read against its site, its
   `<lc>` and `<id>` known, its zone `None`, and one problem saying it is a
   shape no written source gives. The web marks it off-convention, as the
   deployed shape. A KV cluster created on it takes its zone from the
   seed's bare-metal InfraEnvs (ADR-0069).
3. **Placement** never offers it, by its kind (section 4), and a create on
   it is refused as on any seed.

**Rejected:** reading the shape only once a source writes it: until then a
seed so named would be a Customer MCE a viewer could know of.

**Verification:** `packages/wingman-core/tests/unit/domain/test_cluster_kinds.py`
(the shape is a seed, its files KV clusters; the near misses are MCEs),
`apps/day1-service/tests/unit/domain/test_kind_names.py` (its lifecycle,
id, no zone, the problem; never placement's candidate, refused for a
tenant), `apps/day2-service/tests/unit/domain/test_visibility.py` (a KV
cluster on it and its hub are an admin's destinations).
