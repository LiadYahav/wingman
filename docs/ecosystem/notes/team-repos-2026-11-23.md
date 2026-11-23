# The team repos on 2026-11-23: what changed, what is in flight, what touches Wingman

A survey of the platform's repos from about 2026-11-10 to 2026-11-23, made to see where seeds,
KV clusters and VM workers stand ([kubevirt-platform.md](kubevirt-platform.md)) and what Wingman
must follow. Shallow clones of every branch since 2026-11-08 and `gh api` GETs only; nothing was
run, started or written. Paths are relative to each repo (`WM` is this one). Where a note in this
folder was wrong in the present tense it was corrected in the same change; the readiness review
is [`../../ideas/kubevirt-seed-kv-readiness.md`](../../ideas/kubevirt-seed-kv-readiness.md).

| Repo (`team-redbull/…`) | Read at | Newest release |
|---|---|---|
| herzi | `0ef4d2a` (2026-11-07) | v1.2.1 |
| server-scan | `911d2c7` (2026-11-22) | v6.9.2 |
| workflows | `29ef001` (2026-11-22) | `release-2026-11-22-29ef001` |
| redbull-platform | `fb18769` (2026-11-23) | — |
| redbull-brain | `52e251b` (2026-11-23), the last 30 commits | — |

---

## 1. herzi

**Changed:** nothing on `main` since 2026-11-07 (`0ef4d2a`, v1.2.1; the day's last commits follow
the install-server → add-server-to-mce rename and bump Go dependencies).

**In flight:**
- **PR #1** (draft, branch `docs/multi-infraenv-tiering`, `7aec276`, 2026-11-18), docs only,
  `docs/design/used-agents-and-multi-infraenv.md`, "Proposed, not implemented". Part A: herzi
  labels every bound Agent `redbull.io/claimed: "true"`, and collects a free, labelled, settled
  Agent by starting `remove-server-from-mce` (`{server_name, mce_cluster, namespace}`), never by
  its own delete; `dryRunCollect: true` first, at most 3 open removals per pool. Part B: accept an
  `In` over the InfraEnv key plus any `DoesNotExist`, split a NodePool's demand by where its nodes
  are bound. Its open questions include that `remove-server-from-mce` does not destroy a VM (Q4).
  No review; CI red only on `make vuln` (a Go standard-library finding in code it does not touch).
- **Branch `docs/retire-used-servers-plan`** (`578edf1`, 2026-11-19, no PR):
  `docs/review/retire-used-servers-plan.md`, a change plan whose owner decisions D1-D7 it marks
  approved. **It names the label `redbull.io/ever-installed`**, lets a NodePool carry exactly the
  InfraEnv's own `matchLabels` plus that one `DoesNotExist` (§4.2; anything else stays a pool
  problem), holds every removal until every Agent NodePool on the hub carries the expression (the
  retirer's rule 6), starts in dry run, and retires scaled-down servers rather than reusing them
  (§3.4). New metrics `herzi_pool_retiring`, `herzi_retiring_agents{state}`,
  `herzi_agents_labelled_total`, `herzi_label_errors_total`, `herzi_removals_total{result}`.

**Touches Wingman:**
- **Demand** (`internal/pipeline/attribute.go:32-65`): only `platform.type: Agent` NodePools;
  keyed by `matchLabels["infraenvs.agent-install.openshift.io"]`. A NodePool without that label
  loses its demand with a warning (an `In` selector, ADR-0064). **More than one `matchLabels`
  entry, or any `matchExpressions`, blocks the pool** (:48-49): Wingman's `excludeAgentLabels`
  (ADR-0065) and the convention's flavor/size/zone selector both do. Supply and the target are as
  [hosted-clusters.md](hosted-clusters.md) §1.2 says.
- Run ids `add-server-to-mce-<mce>_<infraEnv>_<slot>` and `…_<server>` (`internal/ids/ids.go:13-24`)
  match `WM/apps/day1-service/src/wingman_day1/domain/add_server.py`; its request is
  `{infra_env, mce_cluster, namespace, count}` (`internal/installer/installer.go:105-110`).
- herzi calls no server-scan route, and its RBAC reads Agents only (no label patch today).
- Nothing about VMs, seeds or KV clusters in its code. `docs/design/herzi-design.md:755`: "Nothing
  in workflows creates VMs yet: VM pools run dry"; a VM InfraEnv would be ordered like any pool.
  One release per hub (`config.mceName`), so a seed gets its own.
- Its metrics (`internal/metrics/metrics.go:56-117`, `herzi_pool_*`, `herzi_orders_total`, …):
  Wingman reads none.

---

## 2. server-scan

**Changed** (tags since 2026-11-10; Wingman follows v6.6.0):

| Release | What |
|---|---|
| v5.0.0 `dc0118d` (breaking) | Collectors move to the `deploy/helm/server-scan-collectors` chart; **one KubeVirt collector per KubeVirt cluster**, manager `mgr_kubevirt_<cluster>` (its ADR-0060) |
| v5.1.0 to v5.4.0 | `.xlsx` export, the Confs tab (`GET /api/v1/confs`), a failed server written as a `collection_error` stub instead of aborting the run, events matched by serial and BMC host |
| v6.0.0 `d24866c` (breaking) | `POST /servers/available` locks one server and live-checks it; the `GET` reads stored data and takes `max_health` (its ADR-0063) |
| v6.1.0 to v6.2.0 | The collectors chart can take over the hub's CronJobs; the BMC copy button, a health bar per Sites card |
| v6.3.0 `8251fec` | **`server_type`** (`physical` or `vm`, from the vendor) on rows and detail |
| v6.5.0, v6.6.0 | `POST /servers/{id}/refresh`; Fetch now on every row (Wingman's `synced_at`) |
| v6.7.0 `3a487b4` | A Dell OME profile whose last deployment failed is CRITICAL (a `profile` health category) |
| v6.8.0 `b62cfaf` | `DELETE /servers/{id}` (409 `SERVER_DELETE_BLOCKED` without `?force=true`) |
| v6.9.0 `670ff36` | A Clusters page, admin `GET /api/v1/openshift/clusters` and `POST …/{kind}/{name}/decommission`, a `CLUSTER_NOT_REPORTING` event after 7 days |
| v6.9.2 `911d2c7` | UCS virtual-drive health (`raid.volume_degraded`, `raid.volume_failed`); a KubeVirt diagram |

**In flight:** PR #37 (job times on admin `GET /api/v1/jobs`, an Architecture tab), no Wingman
impact. Closed unmerged on 11-17: PR #26 (maintenance servers out of `AVAILABLE`) and PR #21;
branch `feat/maintenance-unavailable-server-refresh` still carries the maintenance idea.

**Touches Wingman:**
- **The two routes Wingman reads are unchanged since v6.6.0** (`backend/app/api/v1/schemas.py:271-352`
  for the row; the detail adds only `profile_deployment`). `synced_at` can move to v6.9.2 with no
  code change ([`../../integrations/server-scan.md`](../../integrations/server-scan.md)).
- **VMs are rows.** Vendor `kubevirt`, `server_type: vm`, always reachable, `UNKNOWN` when stopped
  (its ADR-0058); its host only on the detail (`vm_host`) and `GET /servers/{id}/vm-host`. Only
  where a KV cluster has its own collector release, whose `clusterName` is that cluster's
  `nodes-status` release name (its ADR-0060 §3-4). Wingman reads no `server_type`, so VM workers
  are servers to its Nodes tab, placement and Inventory Management.
- create-vm names VMs `ocp-<InfraEnv>-<6 hex>` today (workflows `shared/infraenv_names.py`), so the
  `^ocp` filter collects them and classifies them HOSTED_CLUSTER.
- **No zone** in server-scan, and nothing about seeds, KV clusters or `kv<cpu>` pools, although
  the convention makes it the zone's source of truth.
- New health rules can lower a server's overall health, which is all Wingman reads; spare and pool
  counts may drop with no change in shape.
- A cluster Wingman deletes keeps its servers "in use" in server-scan until an admin decommissions
  it there (inferred from its ADR-0067, where the cluster ran its own `nodes-status` release).

---

## 3. workflows

**Changed** (`main`, 2026-11-10 to 2026-11-22; releases `release-2026-11-16-91298e1`,
`release-2026-11-19-5856f96`, `release-2026-11-22-29ef001`):

| Workflow | Commits | What |
|---|---|---|
| provision-cluster (new, the cluster-lifecycle domain) | `ff1aba7` (PR #15, 11-11) to `c619e63` (PR #23, 11-16) | Creates a hosted cluster's day1 file, branch, merge request and day2 folders, then a console shortcut. GitLab only (`7bf4b8e`); `tuningConfigmap` refused in the request (`c619e63`) |
| allocate-segment | `ff1aba7` | **Writes nothing to the day1 repo any more**: `{cluster, site, type=HC}`, `site` required, **`values_branch` a 422** (`workflow_domains/segment_lifecycle/router.py:96-136`); phases validating-site, allocating-segment, verifying-allocation; normally provision-cluster's child |
| add-server-to-mce | `48234f5` (11-17), `6fdfe5d` (11-19), `29ef001` (11-22) | One server per run, allocated by server-scan's `POST /servers/available` (`candidate_count` a 422); **a pool draw by the InfraEnv's `agentLabels`**: pattern `^ocp-<flavor>-<size>-<site>-` from `redbull.io/flavor`, `size`, `site`, each `[a-z0-9]+`; missing labels fail the draw with `InfraEnvAgentLabelsError` (`workflow_domains/server_lifecycle/add_server_to_mce.py:555-608`, `:964-981`). A named install needs no labels |
| uninstall-server-from-hc | `c0dbd68` (11-16), `6fdfe5d` (11-19) | **Ends at a free Agent**: no lock, no `remove-server-from-mce` child, `kept_in_inventory: true` in the result. Runs started 11-12 to 11-17 labelled Agents `redbull.io/uninstalling` |
| update-nodepool (children scale-up-nodepool, scale-down-nodepool) | `43c8ee2` to `aab8949`, fast-forwarded into `main` at `5856f96` (11-19), no PR | One NodePool by name, `server_names` or `scale_down_policy` (not both), `infra_env_kind` a 422 |
| upgrade-cluster, upgrade-targets | — | Unchanged since 11-10 |
| create-vm | `f1870b2` (docs) | Unchanged on `main` (below) |

**In flight:** PR #27 (open, 11-22) moves provision-dell-server off `main` ("not in production"),
removing `/workflows/server-provisioning/*`; branch `feat/provision-dell-server` names Dell servers
by the convention (`ocp-<flavor>-mtl-<site>-<serial>`, at most 32 characters). PR #26 (open,
11-19, docs only) is create-vm's redesign. PR #25 (a multi-InfraEnv NodePool not read as drift)
closed unmerged. PR #8 (Dell template safety) open since 09-30.

**What Wingman starts, against `main`:**
- **provision-cluster** (`workflow_domains/cluster_lifecycle/router.py:95-180`): `?cluster=&mce=`,
  a YAML body. `cluster` with or without `ocp4-`, **its part after `ocp4-` a DNS label of at most 24 characters**
  (`shared/cluster_names.py:99-117`). It checks owner, `mastertag`, a non-empty `nodepool`, config
  names, `clusterName` against the file name and `day2.env` against the MCE folder
  (`activities/cluster_lifecycle/cluster_values.py`), refuses `vlanId`, `dhcp_values`,
  `mcConfigMap`, `tuningConfigmap`, and passes every other key through: `platform: kubevirt`,
  `annotations`, `excludeAgentLabels`, `imageContentSources`. It writes the text as given, then
  `vlanId` and `dhcp_values`. Wingman's call matches
  (`WM/apps/day1-service/src/wingman_day1/infrastructure/provision_workflow.py`). Its last step
  retries forever where the shortcuts service is a placeholder.
- **update-nodepool** (`workflow_domains/server_lifecycle/router.py:851-985`): matches Wingman's
  body exactly (`infrastructure/scale_workflow.py`, `scale_payloads.py`). On redbull-platform's own
  hub `server-lifecycle-worker`, whose chart carries no `day1:` or `argo:` values, a run fails
  with `Day1NotConfiguredError`; the workflows repo's chart has them.
- **add-server-to-mce**: Wingman's body is still valid; what changed is what the InfraEnv must
  carry for a pool draw (its three `agentLabels`).
- **uninstall-server-from-hc**: Wingman's one-name body matches; the outcome changed (above), so
  a server Wingman uninstalls stays in its MCE as a free Agent, and leaving the MCE is a separate
  `remove-server-from-mce` (`{server_name, mce_cluster, namespace}`, which refuses a bound Agent),
  which Wingman does not start. Nothing in remove, uninstall or scale-down is VM-specific: a VM is
  handled as a BareMetalHost and never deleted.
- **upgrade-cluster**: unchanged; Wingman's request matches.

**KubeVirt on `main`:** `POST /workflows/vm-lifecycle/create-vm` (`workflow_domains/vm_lifecycle/router.py:44-179`),
`{mce_cluster, infra_env, namespace, count ≤ 20}`, ids `create-vm-<mce>_<infraEnv>_<slot>`. It takes the
**old** InfraEnv shape `<conf>[-<l>]-zone-<zone>-<cpu>` (`shared/infraenv_names.py:38-40`), lists KV
clusters from `sites/<site>/mces/ocp4-seed-<site>-<zone>/hostedClusters/`
(`activities/vm_lifecycle/day1_repo.py`) and reaches them through the `kv-capacity` and `kv-vm-api`
agents, which nothing deploys, so a run waits. add-server-to-mce's VM branch (create-vm as a child):
"NO branch exists yet" (`CLAUDE.md:971-972`). PR #26's design (a worker per KV cluster, a zone
lock) uses seed `ocp4-<lifecycle>-seed-<site>-<id>` and InfraEnv `<flavor>-kv<cpu>-<site>-<zone>`,
an earlier draft of the convention: the convention since 2026-11-22 puts the zone in seed and KV
names and no site in InfraEnv names.

**Names:** only add-server-to-mce's pool draw follows the convention. `shared/cluster_names.py`
still has the MCE `^ocp4-<env>-mce-<site>-<letter>$` (`:41`), the old `ocp4-seed-` and
`ocp4-kubevirt-` prefixes (`:43-44`), and the 24-character hosted-cluster stem (`:89-117`); no
workflow refuses a KV cluster file without one zone (the convention's open item 10). The
naming-convention skill (`.claude/skills/naming-convention/SKILL.md`) is the only place
`redbull.io/claimed` appears.

**The orchestrator's routes** against [workflows-orchestrator-openapi.json](workflows-orchestrator-openapi.json)
(26 operations): `main` adds `POST /workflows/server-lifecycle/update-nodepool` (27); PR #27 would
remove the two provision-dell-server routes. The saved schemas are stale: `AddServerToMceRequest`
still has `candidate_count` (a 422 now), `AllocateSegmentRequest` still has `values_branch` (a 422
now), and `UpdateNodePoolRequest` is missing. Some accepted fields are hidden from the schema
(add-server's `namespace`, `labels`, `allow_unhealthy`).

**The day1 merge request's VLAN.** allocate-segment no longer writes `vlanId` and `dhcp_values` on a
branch; provision-cluster does, on its own branch. The workflows' guide for the air-gap removes the
day1 CI's allocate call (`APPLY-PROVISION-CLUSTER.md:24-31`) and says a hand-pushed file without
`vlanId` renders its network config with VLAN `None` (`:184-193`); the GitHub day1 mirror dropped its
allocate step (`gitops-day1-platform-config` `8ff90dd`, 11-11). Where the workflows release is
`91298e1` or later, **a cluster created by Wingman's merge request (`DAY1_PROVISIONER=merge-request`,
the default) gets no VLAN**: only `DAY1_PROVISIONER=workflow` does (ADR-0042).

---

## 4. redbull-platform

**Changed:** the cluster-lifecycle worker's chart and services entry (`72defe9`, PR #14, 11-11), then
its token, GitLab day1 and sig repos and console shortcut keys (PRs #15, #16, #18, #19, `65e34f7`);
segment-lifecycle-worker drops its day1 keys (PR #17); a `server-scan-collectors` app with the fake
collector only, the KubeVirt collector present but `enabled: false` (PR #13); PR #20 (11-23) points
the hub at a new lab and leaves the cluster-lifecycle worker's `day2SigRepoUrlTemplate` on the
deleted sandbox "for a later change". Image bumps: orchestrator to v0.1.105 (v0.1.104 carries
update-nodepool, v0.1.105 the label-based draw), server-lifecycle-worker v1.0.64,
cluster-lifecycle-worker v1.0.9, vm-lifecycle-worker v1.0.11, **server-scan 6.9.2**. No open PR.

**What it deploys** (`gitops/appset.yaml` over `gitops/services/*/app.yaml`): the orchestrator,
Temporal, the cluster-, segment-, server- (for one MCE) and vm-lifecycle workers (the hub limb),
segments-manager, server-scan and its collectors, dhcp-scope-manager, cluster-navigator and its
collector, OpenShift Virtualization, kubevirt-redfish, external-secrets and the docs. Charts that
nothing deploys: the upgrade workers, server-provisioning, `kv-capacity`, `kv-vm-api`, and the
chart that would register VMs as Agents. **No seed or KV cluster configuration, and not Wingman.**

**Touches Wingman:** the orchestrator is still `workflows-orchestrator-api:8080` in namespace
`redbull-workflows`; the cluster-lifecycle worker's day1 repo is `gitops-day1/platform-config`
(the project Wingman writes), its sig template `…/redbull/gitops-day2-prod/sigs/{sig}.git`, its
console template keyed by the day1 file stem.

---

## 5. redbull-brain

The team's knowledge base with an MCP search server and a Claude plugin; **no roadmap, plan or
decision log**. Its last 30 commits are automated upstream refreshes. It never mentions Wingman,
seeds, KV clusters or create-vm. `knowledge/gitops/day1-platform-config-values.md` (verified
2026-10-03) still has CI calling allocate-segment with `values_branch`, which is no longer so;
upgrade-cluster writes incident pages into its `incidents/` (none yet).

---

## 6. Not read, or not sure

- Whether the air-gapped day1 CI still calls allocate-segment, and which workflows release the
  air-gap runs.
- Which of herzi's two used-Agent proposals the owner will build.
- The live orchestrator's OpenAPI (the route list above is from the routers), `team-redbull/kv-agents`,
  and the hostedclusters-setup chart's open branches beyond `feat/nodepool-annotations`.
- Whether production hosted clusters run their own `nodes-status` release (server-scan's
  decommission).
