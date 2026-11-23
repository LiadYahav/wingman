# Ready for seeds, KV clusters and VM workers?

**Status:** proposed. A readiness review on 2026-11-23 of Wingman at release 3.53.0
(`origin/main` `dc26b09a`) against the KubeVirt platform as `kubevirt-workflows` describes it
([its study](../ecosystem/notes/kubevirt-platform.md), read at `3ba0835`) and as the team repos
build it ([where they stand](../ecosystem/notes/team-repos-2026-11-23.md)). It changes no code:
each item below becomes work when it is decided. Paths are relative to
`apps/day1-service/src/wingman_day1/` unless they start at the repository root; "the specs
template" is the fixtures' `cluster-template.j2`, in the `wingman/` specs project under
`dev/gitlab-fixtures/`.

Another branch, `roiblum/naming-convention` (not pushed when this was written), is bringing
Wingman's names to the convention and Inventory Management to add-server-to-mce's label-based
pool draw. The items it covers are marked **(naming branch)**.

## The short answer

- **Seeds and KV cluster files are read, but as what they are not.** Every
  `sites/<site>/mces/<x>/` folder is an MCE and every file under its `hostedClusters/` a tenant
  cluster. A seed is listed as an off-convention MCE, a KV cluster as an off-convention hosted
  cluster. Placement and create never use a seed, by accident of the naming rule. **Edit,
  delete, Scale, uninstall and upgrade treat a KV cluster like a tenant's**: deleting its file
  from Wingman removes a cluster that holds other tenants' VMs.
- **A "KubeVirt cluster" in the platform's sense is an agent cluster whose InfraEnvs are
  `kv<cpu>` pools.** Wingman writes those files correctly today. Its `platform: kubevirt` path is
  HyperShift's KubeVirt provider, which the architecture does not use for tenants (C2, AD3); it is
  a lab shape.
- **VM-backed NodePools trip placement's supply check**: a VM pool is built on demand, so it
  rarely holds enough free Agents, and a VM is in server-scan only where its KV cluster runs
  server-scan's KubeVirt collector, a new one only after the collector's next pass. A cluster
  drawing only from VM pools then gets no MCE pick. Inventory Management would order VMs through
  the same add-server route, but its counts are server-scan's. Scale and uninstall work per
  NodePool and per node, VM or not.
- **Not KubeVirt, but first:** since workflows `ff1aba7` (2026-11-11) allocate-segment writes
  nothing to the day1 repo, so a cluster created by Wingman's default merge request
  (`DAY1_PROVISIONER=merge-request`) gets no `vlanId` wherever the workflows release is
  `91298e1` or later and the day1 CI no longer calls it; only `DAY1_PROVISIONER=workflow` does
  ([the survey](../ecosystem/notes/team-repos-2026-11-23.md) §3). And an uninstall now leaves
  the server in its MCE as a free Agent, where Wingman's dialog says it leaves the MCE.
- **Before seeds and KV clusters go live**, Wingman needs: kinds for seeds and KV clusters (with
  the actions that are not a tenant's taken away), the convention's names, a supply check that
  knows VM pools and claimed Agents, the zone on every nodepool, and later the capacity policy
  page (AD31).

## 1. Does Wingman list, show or mis-handle a seed's folder and a KV cluster file?

`dev/gitlab-fixtures` has neither shape: its day1 tree has only Customer MCEs and tenant files
under `sites/site1/` and `sites/site2/`.

| Surface | What happens with a seed `sites/five/mces/ocp4-prod-seed-five-az1-a/` and its KV file `ocp4-prod-kv-five-az1-a.yaml` | Where |
|---|---|---|
| The day1 tree | The seed is an MCE (any directory at `sites/<site>/mces/<x>`), the KV file a cluster (any `<name>.yaml` in `hostedClusters/`) | `application/tree.py:49-67` |
| MCE names | `ocp4-<env>-mce-<site>-<letter>` only, so the seed is "does not follow" and has no env | `domain/names.py:83-96` |
| MCE lists (sites, the create form, flavors' review) | The seed is listed with the off-convention MCEs; the create form lists those apart (`apps/web/app/(app)/clusters/new/page.tsx:635`), a flavor's review leaves them out (`apps/web/components/specs/flavor-editor/review-section.tsx:95`) | `application/sites.py:83-89`, `:124-135` |
| Cluster names | `ocp4-<env>-<name>-<site>[-<seq>]`: after the site comes at most one segment, so `…-five-az1-a` fails. The KV cluster is flagged on the Clusters page (`apps/web/app/(app)/clusters/page.tsx:190`) and its page shows the off-convention notice (`apps/web/components/clusters/cluster-notices.tsx:22`) | `domain/names.py:115-133`; `application/clusters.py:562` |
| Placement (ADR-0050) | Candidates are the site's MCEs whose name gives the env, so a seed is **never** a candidate, and a create under an off-convention MCE is refused | `application/placement.py:262`, `:299-304`; `domain/names.py:194-199` |
| Create | Refused under a seed (above). The reserved flavors are not refused: a flavor named `kv`, `seed` or `mce` makes `ocp4-<env>-kv-<site>-<id>`, and a typed name with `kv` as its `<name>` passes | `domain/names.py:182-212`, `:244-280`; `application/specs.py` (no reserved-name check) |
| Edit and Delete | **No kind check.** An admin can edit or delete a KV cluster's file like a tenant's; the delete MR removes its Application | `application/clusters.py:399-428`, `:430-447` |
| Upgrades | A seed has no `upgrade/mces/<seed>.yaml` today, so no version is offered for its KV clusters; once one exists, a KV cluster is offered `upgrade-cluster` like any cluster | `application/upgrades.py:99`; `domain/openshift_versions.py:151-159` |
| Scale, Nodes tab, uninstall | Offered on a KV cluster, with the seed as its MCE: a scale-down or an uninstall of a hypervisor without evacuating its VMs (procedures 08, 16) | `application/scale.py:101-122`; `application/nodes.py` |
| Inventory Management | The seed is an MCE card with its `-mtl` pools (right: herzi fills them on the seed, AD27), counted by the old `ocp-<infraEnv>` name prefix **(naming branch)**; since 3.54.0 by the InfraEnv's agentLabels (ADR-0057's amendment) | `application/inventory.py:154-171`; `domain/inventory.py:57-73` |
| Quick Links | The seed gets a card like an MCE (its Argo CD and console), which is right: its KV clusters' Applications run on it. It is labelled as an MCE | `domain/quick_links.py`; `application/quick_links.py:50-54` |
| Day2 | Generic: a seed is an MCE hub, a KV cluster a hosted cluster, the env from the name's second segment. A KV cluster's `vm-lifecycle-worker` is a day2 chart, so this is what the platform needs | `apps/day2-service/src/wingman_day2/application/topology.py:142-160`; `apps/day2-service/src/wingman_day2/domain/clusters.py:204` |
| Seed folder files | A seed folder may hold `values.yaml` and `version.yaml` like an MCE's; nothing else in Wingman reads it | `domain/paths.py:44-66` |

Every file under a seed's `hostedClusters/` is an Argo Application on the seed, as under an MCE,
so the existing traps (no placeholder, no sidecar) hold there too.

## 2. KubeVirt hosted clusters (`platform: kubevirt`)

- **The architecture's VM workers are Agents.** A tenant cluster on VMs has NodePools whose
  `infraEnvName` is a `kv<cpu>` pool (`c200-kv32-az1`) on the Agent platform; kubevirt-redfish
  makes each VM install like bare metal (C2, AD3, AD29; acceptance P3). Wingman's create, edit and
  delete write exactly that file today: the InfraEnv name is opaque to them, the template writes
  `infraEnvName` (the specs template, `cluster-template.j2:88`), and the
  chart selects the InfraEnv's Agents. A flavor can list `c200-kv32-az1/2/3` like any pool.
- **`platform: kubevirt` is HyperShift's KubeVirt provider**, a different thing: the
  hostedclusters-setup chart then renders `platform.kubevirt` with `compute.cores`/`memory`,
  `rootVolume`, `additionalNetworks` from the VLAN, and an `infra-kubeconfig` Secret for VMs on
  another cluster (`team-redbull/helm-charts-hostedclusters-setup` `1820ce0`,
  `templates/nodepool.yaml:94-115`, `templates/hc.yaml:121-136`; `kubevirtInfra: local` for VMs on
  the MCE). The only such file in the fixtures is the sandbox upgrade demo
  (`dev/gitlab-fixtures/gitops-day1/platform-config/sites/site1/mces/ocp4-mce-workflow-test/hostedClusters/ocp4-upgrade-demo.yaml`),
  which says "KubeVirt VMs on the MCE, where production uses the Agent platform".
- **What Wingman does with it**: the template writes only `platform: kubevirt` and the nodepools'
  usual keys (the specs template, `cluster-template.j2:60-64`), so the chart's defaults apply (6 cores, 12Gi, a 32Gi
  root volume, external infrastructure). The file contract mirrors the chart (no `infraEnvName`
  needed, `domain/cluster_file.py:303-314`), additional InfraEnvs and excluded labels are refused
  or left out (`domain/nodepool_infra_envs.py:118-142`, `domain/excluded_agent_labels.py:81-82`),
  and drift compares the key (`domain/value_drift.py:304-305`). Correct per the chart, but a
  production create would render a cluster with no infrastructure Secret and default sizes.
- **So:** keep `platform: kubevirt` for the lab, and do not build on it. VM-backed tenant
  clusters need the items in §4, not a KubeVirt platform form.

## 3. Inventory Management, Scale, uninstall and upgrades with VM-backed NodePools

| Feature | With `kv<cpu>` InfraEnvs and VM Agents | Where |
|---|---|---|
| Placement's supply check | Free Agents are counted per InfraEnv label and checked against server-scan's rows. A VM is a row (vendor `kubevirt`, `server_type: vm`) only where its KV cluster runs server-scan's KubeVirt collector, and only after the collector's next pass; until then it is "not in server-scan" and the node type is **unknown, never picked** once healthy servers fall short. A VM pool may also hold few free Agents, because VMs are built on demand (AD14, AD29), and a short pool fails the check. An all-VM cluster gets no pick; an admin cannot override an unknown check | `domain/mce_capacity.py:236-249`, `:337-356`; `domain/placement.py:249-266` |
| Claimed Agents | A free Agent labelled `redbull.io/claimed` is counted as free by placement; the convention says a marked free Agent is not spare (§5 rule 8). The Nodes tab is right, since it applies the NodePool's own selector. Since 3.55.0 placement leaves out a free Agent carrying the used-Agent label (`redbull.io/ever-installed`, the user's choice, or the setting's keys) | `domain/node_pools.py:573-588` (no label check); `domain/mce_capacity.py:351-353`; `domain/node_pools.py:554-570` |
| Inventory Management | Pools and counts come from server-scan rows matched by name prefix (since 3.54.0 the prefix comes from the InfraEnv's agentLabels, ADR-0057's amendment). A VM pool's VMs are rows once collected (create-vm names them `ocp-<InfraEnv>-<6 hex>` today, so the prefix matches; the convention's names would not), but a pool is filled by building VMs, not by installing listed ones. A count still goes through (1 to 20, no cap by availability): add-server-to-mce would build the VM through its `create-vm` child once that branch exists. A named install makes no sense for a VM pool | `domain/inventory.py:57-73`; `application/inventory.py:196-250`; `apps/web/lib/inventory/start.ts:12-21` |
| Scale | One NodePool by name, any pool kind: right for VM NodePools. A scale-down's server picker lists the NodePool's nodes (a VM's BareMetalHost name is the VM's), so naming the VMs that leave works the same. On a KV cluster it is unsafe (§1) | `domain/scale.py`; `application/scale.py:101-122` |
| Uninstall | `uninstall-server-from-hc` by the node's server name, VM or not. Since 2026-11-19 it ends at a free Agent in the MCE and starts no `remove-server-from-mce`; no workflow deletes a VM, and herzi's collector of used Agents is not built, so today an uninstalled VM is reused as it is, against AD23. Wingman's dialog still says the server leaves the MCE (`apps/web/components/clusters/uninstall-node-dialog.tsx:22`, `apps/web/app/(app)/docs/cluster-workflows.tsx:62`). A VM's server-scan link opens its record once collected; day1 reads no `server_type`, so the page does not say it is a VM | `application/nodes.py`; `domain/servers.py` |
| Upgrades | `upgrade-cluster` is per cluster, VM or bare metal alike, InPlace (AD24). On a KV cluster it would roll hypervisors without the evacuation procedure 16 asks for | `application/upgrades.py:140` |
| Zones | Wingman has no zone: a flavor lists one nodepool per pool, and nothing writes `nodeLabels: topology.kubernetes.io/zone` unless a flavor sets it. Tenant spread needs it (AD7); a KV cluster file is refused without it | the specs template (`cluster-template.j2:122-124`) |

## 4. What Wingman should change, in order

| # | Change | Why | Where | Size | Waits on |
|---|---|---|---|---|---|
| 0 | **The default create's VLAN, and the uninstall's words** (not KubeVirt, but first): make `DAY1_PROVISIONER=workflow` the default or refuse a merge-request create where nothing allocates; say an uninstall leaves the server in its MCE, and offer `remove-server-from-mce` where a person takes it out | allocate-segment writes no file since 2026-11-11, so the merge request's cluster has no `vlanId`; uninstall-server-from-hc ends at a free Agent since 2026-11-19 | `settings.py` (`DAY1_PROVISIONER`), ADR-0042, `apps/web/components/clusters/uninstall-node-dialog.tsx:22`, `apps/web/app/(app)/docs/cluster-workflows.tsx:62`, CLAUDE.md's key facts | S | Which workflows release and day1 CI each deployment runs |
| 1 | **Know the cluster kinds**: tell a seed folder and a KV cluster file from an MCE and a tenant by the reserved flavor (`ocp4-<lc>-seed-<site>-<zone>-<id>`, `ocp4-<lc>-kv-<site>-<zone>-<id>`), list them as Seed and KV cluster, and stop flagging them | Today they are "off-convention" MCEs and clusters | `domain/names.py`, `application/tree.py`, `application/sites.py`, the cluster list and notices | M | Nothing: the convention is decided **(naming branch, in part)** |
| 2 | **Take a tenant's actions away from KV clusters**: no Edit, Delete, Scale, uninstall or upgrade from Wingman; a refusal naming the procedure (06-09, 16) | Deleting or shrinking a KV cluster takes down other tenants' VMs; its growth is the KV Capacity Controller's (AD27) | `application/clusters.py:399-447`, `application/scale.py`, `application/nodes.py`, `application/upgrades.py`, the cluster page | S | 1 |
| 3 | **The convention's names on create**: `<id>` required, `mce`/`seed`/`kv` refused as a flavor or a cluster's `<name>`, the reserved names refused as flavor names | Acceptance P7; a tenant named like a KV cluster would be offered to create-vm's placement | `domain/names.py:182-280`, `application/specs.py` | S | Nothing **(naming branch)** |
| 4 | **Inventory by labels**: a pool's servers by the InfraEnv's `agentLabels` (`ocp-<flavor>-<size>-<site>-`, as the workflow draws; the zone once server-scan records one), not `ocp-<infraEnv>` | Convention names break the prefix rule (`c200-mtl-az1` vs `ocp-c200-mtl-five-…`) | `domain/inventory.py:57-73` | M | workflows `29ef001` (merged; an InfraEnv without the three labels now fails every pool draw with `InfraEnvAgentLabelsError`, so Wingman should show a pool's labels and say so) **(naming branch)**. **Done in 3.54.0** (ADR-0057's amendment), without the zone: server-scan records none |
| 5 | **Claimed Agents are not free**: placement counts an Agent carrying a `DAY1_EXCLUDED_AGENT_LABELS` key as not free, as the NodePools will | Placement over-counts supply once the Kyverno policy marks Agents | `domain/node_pools.py:573`, `domain/mce_capacity.py:351` | S | Nothing (useful once the policy marks Agents). **Done in 3.55.0** (ADR-0050's 2026-11-23 amendment): a free Agent carrying the setting's keys, else herzi's `redbull.io/ever-installed`, is no free server (`domain/used_agents.py`) |
| 6 | **Placement knows VM pools**: a `kv<cpu>` node type passes the servers check without free Agents or server-scan rows (a VM pool is built on demand); its capacity is the zone's KV clusters', which create-vm judges | An all-VM cluster gets no MCE today | `domain/mce_capacity.py:236-249`, `domain/placement.py` (ADR-0050 amendment) | M | create-vm's VM branch in add-server-to-mce (AD29); whether create-vm exposes a zone's fit (team question 2) |
| 7 | **The zone on every nodepool**: write `nodeLabels: topology.kubernetes.io/zone` from the InfraEnv's `agentLabels`, and offer flavors as node types across the three zones | AD7 spread; procedure 03's "one NodePool per zone per worker type"; SC1.1 hides zones from tenants | the create inputs, the specs template (`cluster-template.j2`), flavors | M | The chart: does it render `nodeLabels` from the InfraEnv (convention open item 3)? InfraEnvs carrying `agentLabels` |
| 8 | **Set `DAY1_EXCLUDED_AGENT_LABELS`** to the used-Agent label (operator step), then each existing cluster's merge request (ADR-0065), and say so in the upgrade guide | The convention's §5 rule 4, which Wingman already writes per file. herzi's plan holds every removal until every NodePool on the hub excludes the label, so the per-cluster merge requests are on its path | `docs/upgrade/`, `deploy/helm/wingman/values.yaml` docs | S | **The key** (`redbull.io/claimed` in the convention and herzi PR #1, `redbull.io/ever-installed` in herzi's plan); the mark and the backfill; **herzi accepting the `DoesNotExist`** (herzi `main` blocks the pool of any NodePool with a `matchExpressions`); the chart's `excludeAgentLabels` patch; every NodePool `InPlace` |
| 9 | **The capacity policy page**: show and edit `maxNodes`, `freeCpuPercent`, `standbyWorkers`, `standbyClusters` by merge request | AD31 names Wingman as its editor | a new GitLab-backed page | M | The file's path and owner in the platform repo (O4); its schema |
| 10 | **Removal options from the orchestrator**: draw the scale-down form from `removal-options` (choose nodes only on control plane 4.19+), show refusals verbatim | Draft animation 20; acceptance M7, M8 | the Scale tab | S | The orchestrator route (proposed, not built) |
| 11 | **Fixtures**: a seed folder with two KV files (one zone each, one with a missing zone label), VM pools `c200-kv32-az1/2/3`, a tenant on VM pools, convention names at a 4-letter site | Every item above needs a tree to test against | `dev/gitlab-fixtures/`, `dev/fleet-fixtures/` | S | 1 |
| 12 | **Say which nodes are VMs**: read server-scan's `server_type` (and, for a VM, its KV cluster from the detail's `vm_host` if wanted) on the Nodes tab and in Inventory Management; a VM not yet collected reads "VM, not in server-scan yet" | Today a VM is a server like any other, or a missing one | `domain/servers.py`, `integrations/server_scan/infrastructure/parse.py`, the Nodes tab | S | Nothing (server-scan v6.3.0 sends `server_type`); a collector release per KV cluster for the rows to exist |
| 13 | **`platform: kubevirt` marked lab-only** in the template's comment and the flavor form | It is not the production model (§2) | the specs template (`cluster-template.j2:60-64`), the docs page `apps/web/app/(app)/docs/clusters.tsx:133` | S | Nothing |
| 14 | **A KV cluster view (read only)**: per zone, the seed, its KV clusters oldest first, their role (active, standby, full) and free CPU | The capacity controller's state, for the platform team | a page reading the controller's metrics or the seed | L | The KV Capacity Controller (specification only) |

Item 0 is needed now; items 1 to 5 before the first seed folder is merged; 6 to 8 before the first VM pool
serves a tenant; 9 to 14 when their dependency ships.

## 5. Questions for the team

1. **Is a KV cluster ever edited by hand?** If only the KV Capacity Controller and
   `provision-cluster` write its file, item 2 refuses every edit; if an operator may, Wingman keeps
   Edit for admins and refuses only Delete and Scale.
2. **How does a tenant create learn that a zone's KV clusters can take its VMs?** create-vm fails
   with `NoKvClusterFitsError` at install time, after the create has merged. Wingman's placement
   could ask the same figures before (item 6), or accept that a VM pool may sit short.
3. **Who writes a tenant nodepool's zone `nodeLabels`**: the file (Wingman), or the chart from the
   InfraEnv (item 7)?
4. **Scale by node type** (acceptance M4, M5) against update-nodepool's one-NodePool rule since
   2026-11-18: which one stands?
5. **Flavor names with dashes** (`agent-standard`) under `ocp4-<lifecycle>-<flavor>-<site>-<id>`
   with sites that have dashes: may a cluster flavor hold a dash?
6. **The capacity policy file**: which repo and path, and who approves its merge requests?
7. **The used-Agent label's key**: `redbull.io/claimed` (the convention, herzi PR #1) or
   `redbull.io/ever-installed` (herzi's `docs/retire-used-servers-plan`)? Wingman's setting takes
   either; herzi's plan accepts exactly one key. **Decided (the user, 2026-11-23):
   `redbull.io/ever-installed`**, unlike the convention (ADR-0065's amendment); the setting stays
   empty until herzi ships it.
8. **The seed folder's name**: create-vm on `main` reads `ocp4-seed-<site>-<zone>`, its redesign
   (workflows PR #26) `ocp4-<lifecycle>-seed-<site>-<id>`, the convention
   `ocp4-<lifecycle>-seed-<site>-<zone>-<id>`. Wingman's kinds (item 1) follow the convention;
   the first seed folder must be named so for create-vm to find its KV clusters.
