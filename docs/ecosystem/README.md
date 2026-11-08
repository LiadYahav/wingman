# Wingman and the RedBull ecosystem

What we learned on 2026-11-07 when we re-read the platform the team built over the last 6 months, so that Wingman can come back on top of it. The detailed notes per system are in [`notes/`](notes/). Commits read are listed under [Sources](#sources).

> **Day1 status: there is no Day1 (create-cluster) workflow yet. It is planned and in progress.** Nothing about it exists in code, queues or the orchestrator API. Only the design exists (see [Day1 workflow: planned](#day1-workflow-planned-not-built)).

## TL;DR

- **Wingman writes to the right place but the wrong content.**
  - It already opens an MR that adds one file per cluster at `sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml`. That is the exact file the new GitOps flow consumes.
  - But it renders a full multi-document YAML from a Jinja spec template. The new `hostedclusters-setup` chart wants a short values file: `owner`, `mastertag`, `nodepool[]`.
- **Each system now owns one kind of data:**
  - server-scan: servers.
  - segments-manager: VLAN segments.
  - herzi: keeps InfraEnv pools full by starting workflows.
  - Temporal workflows: all automation.
  - Git + ArgoCD: desired state.

  Wingman knows none of these today. It has no idea of a server, a segment or a pool, and it never calls a workflow.
- **How the team wants portals to behave:** the portal starts a workflow or opens an MR, workflows write Git, a human merge is the approval, and ArgoCD applies. The orchestrator already has a placeholder for a "ClickCluster Platform UI", and Wingman is the natural fit.
- **Until the Day1 workflow exists, Wingman can fill that gap.**
  - Write the short values file through an MR, and let the day1 CI run `allocate-segment`.
  - Show the CI and allocation progress, then the cluster status after merge.
  - Keep this behind an adapter, so it can later switch to starting the `create-cluster` workflow.
- **Day2 has drifted the most.** The day2 repos were reorganized (sites/env levels, fleet defaults, exclusions, OCP-version pins, UPI). Wingman's day2 still assumes the old `mces/<mce>/<cluster>/<addon>` layout.
- **The orchestrator API has no auth.** The user accepts this (see [Decisions](#decisions-2026-11-07)). Wingman still proxies it through its own RBAC.

## Ecosystem map

| Component | Owns (source of truth for) | Store | Read API | Write path | Auth | What Wingman should do |
|---|---|---|---|---|---|---|
| **server-scan** | Physical servers (about 2.5k): BMC, MACs, hardware, health, site, free or in use, maintenance, install reservation lock | MongoDB (Redis is only a cache). Vendor collectors run every 3 h; `nodes-status` jobs run every 5 min | `GET /api/v1/sites`, `/api/v1/servers` (filters incl. `site_id`, `cluster_name`, `openshift_state`), `/api/v1/servers/rows` (whole fleet, ETag), `/api/v1/servers/{id}` | Admin only: `POST/DELETE /servers/{id}/reservation`, maintenance PUT/DELETE | Humans: AD/LDAP session (not OpenShift OAuth). Machines: static bearer tokens (admin/auditor/viewer) | **Read** with a viewer token: sites, MCEs per site, free capacity per MCE and hardware type, node hardware and health per cluster. **Never** call `/servers/available` (a GET with side effects) or reservations; those belong to workflows |
| **segments-manager** | Per-site pool of VLAN segments (/24) and which cluster holds each | MongoDB | Open (no token): `GET /api/sites`, `/api/stats`, `/api/segments?site=&status=&type=` (no cluster filter), `/search?q=`, `/by-segment` | `POST /api/segments/allocate`, `/release`, ... with one static bearer token held only by the workflow worker | Reads open; writes need one shared token | **Read**: site list, free segments per site (block create when none), a cluster's VLAN/CIDR/EPG. **Never write**: allocation is done by the `allocate-segment` workflow |
| **workflows** (Temporal + orchestrator API) | All automation that changes things | Temporal | `GET /workflows/runs/{id}`, `GET /workflows/runs?workflow_type=<Class>` | `POST /workflows/<domain>/<workflow>` → 202 `{workflow_id, run_id}` | **None** (anyone who can reach the Route) | **Call from Wingman's backend as a proxy** (AdminUser for POST, CurrentUser for GET, fill `by`/`requested_by` from the JWT), show runs and progress |
| **herzi** | Keeping each InfraEnv pool filled with ready Agents | No CRD or status object. Reads InfraEnv/Agent/NodePool and Temporal | Prometheus metrics `herzi_pool_demand/_need/_blocked{reason}`, InfraEnv annotations `herzi.redbull.io/state`, `blocked-until` | Starts `add-server-to-mce` (≤20 per call, ≤15 open per pool) | n/a | **Read** pool state; check that a cluster's InfraEnv pool is managed and live before creating it |
| **hostedclusters-setup chart** | Renders HostedCluster, NodePools, NodePool ConfigMaps and the Crossplane DHCP scope from layered values | Git (day1 repo) | n/a | ArgoCD renders on merge to `main` | n/a | **Produce the short values file**, nothing more |
| **gitops-day2** | Per-team addon (chart) deployment on every cluster type | A GitLab group of team repos (`sigs/<team>`) plus the `argocd-day2-platform` charts | n/a (a folder existing is the registration) | MRs to team repos | n/a | **Rewrite Wingman day2** to the new folder rules |
| **kubevirt-workflows** | Design for KubeVirt tenant clusters and the inventory "slot" model, plus 18 procedures | Docs, flow animations, one Python prototype | n/a | n/a | n/a | Holds the **Day1 workflow spec** (procedure 03) and the future self-service catalog flows |

## How a hosted cluster gets created today

This flow is git plus CI, not one workflow.

**Prerequisites. Each is run separately, and some have no owner:**
- Segments exist in segments-manager (operators run `initialize-segment`).
- Servers are in server-scan (the collectors).
- **An InfraEnv exists.** Nothing in any repo we read creates InfraEnvs.
- The InfraEnv's pool is filled by `add-server-to-mce`, started by herzi or by hand.
  - **herzi defaults every pool to dry run (`dryRunGrow: true`) and has not been run on a real hub yet**, so today nothing may actually order servers.

**Flow:**

| # | Step | Who | Automated? |
|---|---|---|---|
| 1 | Write `sites/<site>/mces/<mce>/hostedClusters/ocp4-<name>.yaml` on a non-main branch of the day1 repo and open an MR | A person (Wingman does this today) | Manual |
| 2 | The branch push starts day1 CI. CI calls `POST /workflows/segment-lifecycle/allocate-segment {cluster, values_branch, type: "HC"}`. The workflow allocates the lowest free VLAN in segments-manager and commits `vlanId` + `dhcp_values` back to the branch with `[skip ci]`. CI then renders `mcFiles`/`mcConfigMap` and commits again | CI + workflow | Automated |
| 3 | Merge to `main`. This is the approval | A person | Manual |
| 4 | The ArgoCD tier-3 ApplicationSet on the MCE makes one Application per file. The chart renders HostedCluster `openshift-<cn>` in namespace `hcp-<cn>`, NodePool ConfigMaps, NodePools and the Crossplane DHCP scope. The exported values set no auto-sync for these Applications (**verify on a live MCE**) | ArgoCD | Automated (sync possibly manual) |
| 5 | HyperShift brings up the control plane. NodePools claim Agents from the InfraEnv, and herzi tops the pool up | HyperShift, herzi | Automated (where herzi is live) |
| 6 | **Delete:** remove the file through an MR. In the sandbox chart a PostDelete hook runs `release-segment`. **The production chart has no such hook, so the segment is never released** | A person + hook | Partly |

**Manual or unowned today:**
- choosing parameters and writing the file
- the merge
- possibly the ArgoCD sync
- per-cluster Secrets (the sandbox chart renders none)
- creating InfraEnvs
- switching herzi pools live
- day2 registration in production
- a single "your cluster is ready" signal
- deletion in production
- onboarding a new MCE

### Day1 workflow: planned, not built

- **Status:** no code, task queue or API route. We checked the live orchestrator API on 2026-11-07, and the user confirmed the work is in progress.
- **Planned in the workflows repo:**
  - `create-cluster` (`workflows/CLAUDE.md:818-843`, `shared/models/segment_lifecycle.py:287,365`): runs `allocate-segment` as a child workflow, merges after it returns, then checks the DHCP scope after the merge.
  - `deprovision-cluster` (`workflows/CLAUDE.md:859-872`): replaces today's ArgoCD PostDelete hook.
- **Design spec:** `kubevirt-workflows/docs/procedures/03-create-hosted-cluster.md`.
  - Workflow id: `create-hosted-cluster-<cluster>`.
  - Inputs:
    - `cluster`, `hub`
    - `release_image` (by digest)
    - `worker_types` with per-zone replicas (at least 3)
    - `values_branch`
    - pull-secret and ssh-key refs
  - Steps: validate, allocate segment, verify it, compose the file, commit, human merge, wait for the control plane. The flow is "done" before the workers are ready.
  - Delete is procedure 05.
- **Open questions in the spec:**
  - Who picks the hub/MCE? ("It is an input until something owns it.")
  - Does the merge stay manual?
  - Can one cluster mix worker types?
  - There is no capacity admission check yet.

## The day1 values contract (what Wingman should write)

The chart merges values in layers, and the last one wins:

1. chart `values.yaml`
2. `sites/configValues.yaml`
3. `sites/<site>/values.yaml`
4. `sites/<site>/mces/<mce>/values.yaml`
5. the cluster file

`clusterName` is a separate parameter, taken from the file name.

**A person or portal writes:**

```yaml
# sites/site-a/mces/cluster-mce-site-a-prep/hostedClusters/ocp4-test-storage-site-a-a.yaml
owner: {merkaz: "<unit>", anaf: "<unit>", mador: "<unit>"}
mastertag: 4.22.8                 # required; a bare version gets "-x86_64"
nodepool:
- infraEnvName: dell-r660-site-a-128c-1024gb-5tb
  replicas: 2
  labels: {allowDeletion: false}
  configs: [{name: nm-conf-test-storage-site-a-a-dell-data}, {name: worker-kubeletconfig-reserved}]
  # name: <pool>                  # needed only when two pools share an InfraEnv
```

**Optional per-cluster fields:**
- `platform: kubevirt` with cores, memory, size, storageClass, vlan
- `nodeLabels`, `tuningConfig`, `upgradeType`
- `imageContentSources`, `workertag`, `pausedUntil`

**Written only by automation. Wingman must never write these:**
- `vlanId`, `dhcp_values` (the allocate-segment workflow)
- `mcFiles`, `mcConfigMap` (CI)
- Secrets

**Set at the MCE or global level, not per cluster:**
- image paths, etcd, DNS zone/site, certificates, registries
- `serviceType`, `loadbalancer.addresspool`, `baseDomain`
- the `disable*` switches, secret names, `day2.copy_to_sigs`

There is no API/ingress VIP value. The API is a MetalLB LoadBalancer, a NodePort or the HyperShift default, and DNS comes from Crossplane CNAMEs pointing at AVI.

**Network values come from elsewhere:** the gateway is `.254`, the DHCP range is `.1–.253`, and node IPs come from DHCP.

**There are two copies of the chart and the repos. Decide which is canonical** (see [Open questions](#open-questions-for-the-team)):

| | Production (air-gapped) | Sandbox (connected) |
|---|---|---|
| Git host | GitLab | GitHub |
| Values repo | `gitops-day1/platform-config` | `team-redbull/day1` |
| Chart | `helm-charts/hostedclusters-setup` | `team-redbull/helm-charts-hostedclusters-setup` |
| ApplicationSets | `gitops-day1/argocd-platform` (sanitized copy in `~/Downloads/stack-export`) | — |
| `clusterName` passed to the chart | The file's own `clusterName` if set, else the file name minus `.yaml` and `clusterFilePrefix: ocp4-` (`argocd-platform/hostedClusters/templates/hcAppset.yaml:35`, `values.yaml:9`). `ocp4-prod-herzi-site1.yaml` → HostedCluster `openshift-prod-herzi-site1` in `hcp-prod-herzi-site1` | The full file stem (`gitops-day1-argocd-platform` hcAppset). The chart uses it as is (`hc.clusterName` = `required .Values.clusterName`) → `openshift-ocp4-prod-herzi-site1` in `hcp-ocp4-prod-herzi-site1`. The comments in `_hostedcluster-helpers.tpl:20` and `ocp4-upgrade-demo.yaml` that say the prefix is stripped are **stale**; verified by `helm template` on 2026-11-07 |
| Extras | Certificates, DNS records, CA, Velero, logging, owner ConfigMap, kubeconfig sync, Secrets | HostedCluster/NodePools behind `hostedCluster.enabled`, day2 registration Job, PostDelete segment release, no Secrets |

## Workflows that exist today

All of these are registered in `workflow_domains/main_worker_init.py` and routed in the live API.

| Group | Workflow | What it does |
|---|---|---|
| Segments (hub worker) | `initialize-segment` | Create a segment in segments-manager |
| | `allocate-segment` `{cluster, values_branch, type=HC}` | Reserve an HC VLAN and push `vlanId` + `dhcp_values` to the day1 branch (`[skip ci]`). Run id `allocate-segment-HC-<cluster>` |
| | `release-segment` `{cluster}` | Delete a leftover DHCP scope, then release the segment |
| Servers into an MCE (worker inside each MCE, queue `server-lifecycle-activity-<mce>`) | `add-server-to-mce` | Pick a server from server-scan and lock it, create the BMC Secret, BareMetalHost and NMStateConfig, then wait up to 1 h for the Agent. herzi calls this |
| | `remove-server-from-mce`, `uninstall-server-from-hc`, `publish-infraenv-to-pxe-server` | Reverse paths and PXE publishing |
| Servers (not deployed) | `provision-dell-server` | iDRAC IP to configured server (OME template, RAID, naming) |
| KubeVirt (not on redbull-platform main yet) | `create-vm` | One KubeVirt VM per InfraEnv slot |
| Cluster upgrade (sandbox only) | `upgrade-cluster` (child `upgrade-control-plane`), `upgrade-targets` (synchronous GET) | Changes only day1 git, then syncs ArgoCD. People make 10 kinds of decisions on a run, each sent as a Temporal Update. Also calls an LLM agent service and writes to a "Brain" repo |
| Old names | `install-server` and three others | Kept only so old runs can finish; their routes return 410 |

- **There are no day2/addon workflows and no UPI workflow.** UPI installs are manual.
- **Live sandbox:** only `upgrade-cluster` has ever run (8 runs on `ocp4-upgrade-demo`).
- **Don't trust the list endpoint for existence:** it returns `[]` even for unknown types.

### Orchestrator API cheat sheet

The live spec is saved in [`notes/workflows-orchestrator-openapi.json`](notes/workflows-orchestrator-openapi.json): 25 operations and 38 schemas.

- **Start:** `POST /workflows/<domain>/<workflow>`
  - Returns 202 `{workflow_id, run_id}`, or a per-run report for bulk/`count` requests.
  - Other codes: 409 already running (ids are deterministic, which makes them the dedup key), 422 validation failed, 410 renamed, 502 Temporal refused.
- **Status:** `GET /workflows/runs/{id}`
  - Returns the status, plus `progress` (while running and after a failure), `result` (when done) and `error` (with the root-cause type name).
- **List:** `GET /workflows/runs?workflow_type=<ClassName>&limit≤200`
  - Filters by type only, so per-cluster views must filter on the id prefix.
- **Missing:** no endpoint that lists workflow types, no generic cancel (only upgrade-cluster's abort), no history, no streaming. Callers poll; the temporary pages poll every 10 s.
- **Request bodies are strict pydantic models exposed as JSON Schema in `/openapi.json`, so forms can be generated from them.** Caveats:
  - Cross-field and naming rules exist only on the server and come back as 422s.
  - `progress`/`result` are untyped in the OpenAPI; the real models are in `shared/models/*.py`.
  - Dropdown data (MCEs, InfraEnvs, releases) is not in the schema.
- **The slot model** for KubeVirt and InfraEnv pools:
  - It is one run per machine, with id `<wf>-<mce>_<pool>_<n>`.
  - `count` in a bulk request is **added on top**, not a target, so the caller must subtract runs already in flight.
- **Internal address:** `workflows-orchestrator-api.redbull-workflows.svc:8080`. The temporary pages `/ui/server-lifecycle` and `/ui/cluster-upgrade` are explicitly waiting for the "ClickCluster Platform UI".

## Day2 today (gitops-day2)

`team-redbull/gitops-day2-prod` is a 4-commit mock of separate air-gapped GitLab projects:
- **`argocd-day2-platform`:** five Helm charts that only render Argo objects, chained groups → mces → clusters → operators → deploy.
- **`sigs/<team>`:** one repo per team; there are five in the air-gap.
- **`helm-charts/<chart>`:** one repo per chart, with one frozen branch per release.

It is not limited to the redbull team or to non-OCP clusters. "redbull" is the infra/SRE team's repo (`sigs/redbull`), and every target is OpenShift. Clusters differ by kind: hub, MCE, hosted, UPI.

- **Discovery:**
  - An ApplicationSet with a GitLab `scmProvider` generator scans the group; every repo in it is a team.
  - Everything else is found by git `directories:` generators. **A folder existing is the whole registration.**
  - Folder basename = Argo cluster name = day1 file name.
- **Team repo layout:**
  - Clusters under an MCE: `sites/<site>/<env>/mces/<mce>/{in-cluster | <hosted-cluster>}/<chart>/{<chart>.yaml, values.yaml}`
  - Standalone (UPI) clusters: `sites/<site>/<env>/upi/<cluster>/...`
  - Team-wide chart defaults: `operators/<chart>/`, plus `ocp-versions/<full-version>/`
  - Fleet-wide charts: `defaults/{hub, mces, hosted-clusters, upi}/`, with an optional `exclusions.yaml`
- **Values:** workload values merge through 10 optional layers, ending at `<cluster>/<chart>/values.yaml`. The `<chart>.yaml` deploy config holds `repourl` (must be lowercase), `targetRevision`, `path`, `projectNamespace` and `syncPolicy`.
- **Versions:**
  - A cluster's OCP version comes from day1 `mastertag`.
  - Chart pins have three levels: team default, per-OCP-version (`ocp-versions/`), and a per-cluster **emergency** pin.
- **Behavior to know:**
  - Leaf apps are manual-sync, so nothing deploys until someone syncs.
  - **Deleting the folder orphans the workload; it keeps running.**
  - A chart must not also sit in `defaults/hosted-clusters/`, or two apps get the same name.
- **Air-gap state is unclear:** the latest commit says it is "without Phase F and without `tools/`", and as of 2026-08-20 it was still on the legacy layout. Confirm with the team.

Example: install cert-manager on hosted cluster `ocp4-prod-herzi-site1` (one MR on `sigs/redbull`):

```
sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1/cert-manager/cert-manager.yaml
  repourl: https://<gl>/<top>/helm-charts/cert-manager.git   # only if operators/ has no default
  projectNamespace: cert-manager
  # targetRevision only as an emergency pin
sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1/cert-manager/values.yaml   # top layer, always wins
```

This produces the ArgoCD app `redbull-ocp4-prod-herzi-site1-cert-manager-deploy` on the MCE's Argo.

## How the team wants portals to behave (kubevirt-workflows)

- **The portal starts workflows; the workflow writes Git.** "Customer, via the self-service catalog or a ticket"; "Writes | Git only"; Temporal "exclusively mutat[es] the declarative SSOT".
- **Approval is a human merge:** "Merge to main. ArgoCD only reads main."
- **Requests carry absolute values:** "Absolute, never deltas."
- **Workflow ids are the dedup key.**
- **There are no quotas yet:** "Admission, which does not exist yet ... needs a pre-flight that either rejects the request with a capacity reason or accepts it with an honest estimate."
- **Flows finish early:** "Not at workers ready".

KubeVirt platform model:
- Each zone has a bare-metal Seed cluster that hosts the control planes of the KubeVirt clusters.
- Customer MCE hubs (one per OCP version band) host tenant hosted clusters.
- Tenant workers are VMs acting as Agents, with three NodePools per cluster.
- Pools are one InfraEnv per node type and zone, with warm pools of ready Agents.

Tenant flows: create (03), scale a NodePool (04), delete (05), upgrade the control plane and then workers (14, 13), migrate the version band (18). The HTML files in that repo are step-through flow animations, not UI mockups.

## Wingman today: keep, replace, fix

**Keep (generic and reusable):**
- The UI shell and design system (modernized in PR #16): review dialog, diff viewer, MR progress.
- OpenShift OAuth → app JWT → admin/viewer RBAC.
- The GitLab MR engine: atomic commit → MR → edit, approve or reject, with aggregated approvals. It can front any GitOps repo (day1 values, gitops-day2 team repos).
- Audit, and the layered Helm-values editor with provenance.
- The day1 path layout `sites/{site}/mces/{mce}/hostedClusters/{cluster}.yaml`, one file per cluster, and the live InfraEnv list from the MCE hub.
- Branch names `platform/{user}/...`, which pass allocate-segment's branch checks.

**Replace (tied to the old model):**
- **Day1 rendering:** today it is one Jinja `cluster-template.j2` from the specs repo, rendered with `StrictUndefined` into multi-document YAML, with `# specName:` comment headers. It should produce the short values file instead; specs become presets for those values.
- **Site and MCE as Git folders created with `.gitkeep` MRs:** sites should come from segments-manager/server-scan, and MCE onboarding is a separate process.
- **Choosing an InfraEnv by free text or name:** it should be picked from live pools, with herzi and capacity information.
- **Status read only from the hubs:** it should also show the CI pipeline, the allocate-segment run, ArgoCD, the HostedCluster/NodePools and herzi metrics.
- **The whole Day2 path model:** it should follow the new folder rules (see mismatches below).

**Day2 mismatches against the new layout:**
- **Paths:** it uses the legacy path `mces/{mce}/{cluster}/{addon}` (`config.py:37`), with no site/env, and every endpoint requires `mce`. It has no support for MCE in-cluster, UPI or hub targets.
- **Fleet defaults:** it ignores `defaults/` and `exclusions.yaml`, so installed lists under-report, and installing a chart that is already a fleet default creates a duplicate app name.
- **Values merge:** it merges 3 layers where the platform merges 10. The Helm values fetcher ignores the deploy config's `path`.
- **Versions:**
  - It ignores `ocp-versions/` and day1 `mastertag`.
  - It assumes branch `main` where the platform defaults to `HEAD`.
  - It writes a per-cluster `targetRevision`, which now means an emergency pin that detaches the cluster from fleet upgrades.
- **Dependencies:** it reads a `dependencies:` key from `operators/<c>/values.yaml`, but that file goes to Helm verbatim, so the key would become a chart value.
- **No ArgoCD sync or status:** "install" doesn't deploy, and "remove" only orphans the workload.

**Bugs to fix before reusing anything:**
- Create drops addon overrides, and spec addons are not installed. They show up later as "missing" drift.
- Approvals cache-key mismatch: writes clear `approvals:day1:list`, but the real key is `approvals:combined:list`.
- Day2 approvals look MRs up by IID across team projects, so two teams' `!5` collide.
- The audit MR expand returns 422 for Day1 MRs.
- The status service doesn't match the chart's naming: the chart creates HostedCluster `openshift-<clusterName>` in `hcp-<clusterName>`. Re-check after the `ocp4-` prefix question is settled.
- **Every file in `hostedClusters/` becomes an ArgoCD Application** (confirmed):
  - The tier-3 generator is `files: sites/<site>/mces/<mce>/hostedClusters/*`, and its comment says an empty file "fails the generator rather than being skipped" (`gitops-day1-argocd-platform/hostedClusters/templates/hcAppset.yaml`).
  - **When Wingman creates an MCE, it writes an empty `hostedClusters/.gitkeep` (`cluster_service.py:531`), which breaks that MCE's ApplicationSet.**
  - The `<cluster>.wingman.yaml` sidecars it reads from the same folder (it never writes them) would each become a bogus Application.
- `sync-yaml` and YAML drift can't work, because no variables are stored.
- GitLab is called synchronously on the event loop in `create_cluster` and in several write and approval paths.
- `bulk_install` titles its MRs `[Day2] ...` instead of `[Wingman/Day2] ...`.
- `list_open_mrs` hard-codes target branch `main`.
- There are no Python tests, and CI's `|| echo` swallows pytest failures.

## Proposed direction (phased)

This is a proposal to discuss, not a decision. Each phase is usable on its own.

0. **Clean-up:** fix the bugs above, add Python tests and make CI fail on them.
1. **Read-only integration (low risk, high value):**
   - Sites from segments-manager `/api/sites` (cross-checked with server-scan `/api/v1/sites`).
   - Free segments per site, capacity per MCE and InfraEnv from server-scan `/rows`, and herzi pool state.
   - Node hardware and health per cluster, and orchestrator runs per cluster.
   - Needs a server-scan viewer token in a Secret.
2. **Day1 v2: fill the gap until the workflow exists:**
   - Write the short values file through an MR; specs become presets.
   - Check before the MR:
     - name rules and uniqueness
     - the InfraEnv exists and its pool is live
     - config names exist in `mc-files/`
     - free segments exist at the site
   - After the push, track the CI pipeline and the `allocate-segment-HC-<cluster>` run, and only then mark the MR "ready to merge". Never force-push a branch that CI has committed to.
   - After the merge, show status from ArgoCD + HostedCluster + NodePools + herzi.
   - Put this behind a `ClusterProvisioner` adapter (GitMR now, `create-cluster` workflow later).
3. **Workflow actions:**
   - Proxy the orchestrator through Wingman's backend and generate forms from its OpenAPI.
   - Run pages.
   - `upgrade-cluster` with its decision buttons on the cluster page.
   - Add, remove or uninstall servers, `publish-infraenv` and `create-vm` on the MCE page.
4. **Day2 v2 on the new gitops-day2 layout:**
   - Discover clusters by directory plus day1 `mastertag`, and model the four cluster kinds.
   - Build the full merge with provenance per layer.
   - Check before the MR: defaults vs per-cluster, lowercase `repourl`, and a warning before an emergency pin.
   - Make OCP-version pins a first-class edit.
   - Show ArgoCD status and offer Sync; let removal choose between orphaning and full teardown.
5. **Switch when the workflows land:**
   - Point the Day1 adapter at `create-cluster` and deletion at `deprovision-cluster`.
   - Expose the KubeVirt tenant flows (create, scale, upgrade, delete) as the self-service catalog.

## Decisions (2026-11-07)

- **Wingman owns Day1 for now.** It renders the day1 values file and opens the MR. When the `create-cluster` workflow is ready, Wingman switches to starting it (the `ClusterProvisioner` adapter in phase 2 exists for this), and the Jinja template moves or retires with it.
- **Orchestrator API without auth is acceptable** (user decision). It is no longer a blocker for phase 3.
- **The quality bar is server-scan and herzi.** Wingman's code, tests, CI and docs must not be lower than theirs.
- **Order:** first make Wingman work correctly against the current day1 (`gitops-day1/platform-config`) and day2 (`sigs/<team>`) layouts, and only then add ecosystem features.

## Vision: Wingman as the one platform (later)

Once the basics work, Wingman becomes the single place that ties the ecosystem together. One idea from the user:
- On a hosted cluster's page, show the servers under it: server-scan `GET /api/v1/servers?cluster_name=<cluster>`, plus `mce_name`, health and hardware.
- Clicking a node jumps to that server's page in server-scan.

Related prior art to reuse rather than duplicate: **cluster-navigator** (`team-redbull/cluster-navigator`) is "one place to see every OpenShift cluster": type, segment, router address, version, network. It replaces ClickCluster-Navigator and an operator-based tool called Axiom.

## Open questions for the team

1. **Canonical day1 repo and chart:** GitLab production or GitHub sandbox? They differ (Secrets, PostDelete release, day2 registration), and the sandbox README says this is undecided. The workflows `.env.example` points the day1 repo at GitHub, while its docs describe a GitLab pipeline.
2. **`clusterName` derivation differs between production and sandbox** (see the table above). It changes the HostedCluster and namespace names Wingman reads status from, and the sandbox release hook posts `.Values.clusterName` (the full stem), which matches the allocated `cluster_name` only there. Which one is right?
3. **Off-convention names:** `ocp4-upgrade-demo` and MCE `ocp4-mce-workflow-test` don't match `ocp4-<env>-<name>-<site>`. The chart's day2 registration derives `<env>` from these names and fails on them. Should Wingman refuse such names, or allow them with `day2.env` set explicitly?
4. **Hub/MCE choice:** who picks the hub/MCE, now that Wingman owns Day1? (Also the first question in `docs/ideas/architecture-fit.md`.)
5. **The merge:** does it stay a manual human approval? Is it done in Wingman's approvals page or in GitLab?
6. **Orchestrator auth:** decided, see [Decisions](#decisions-2026-11-07).
7. **Site codes don't match across sandboxes:** segments-manager `site1/2/3`, server-scan `nyc, tlv, bat-yam, five`, stack-export `site-a`. What is the canonical site token? segments-manager assumes it is the same token everywhere (its env key, the day1 path, the MCE name).
8. **InfraEnv naming differs across docs:** `hp-gen11-nyc-64c-128gb` (server-scan; its server pool is `^ocp-<infraEnv>`), `<conf>-zone-<z>-metal|<cpu>` (workflows), `dell-r660-site-a-128c-1024gb-5tb` (stack-export).
9. **InfraEnvs:** who creates them? Nothing in the repos does.
10. **ArgoCD sync for per-cluster day1 apps:** auto or manual?
11. **Air-gapped gitops-day2:** which phase is it on?
12. **Deletion in production:** who releases the segment? **Answered (user, 2026-11-08):** the delete-cluster workflow, as allocation belongs to the day1 workflow. Wingman releases nothing.

## Naming conventions cheat sheet

- **MCE:** `ocp4-<env>-mce-<site>-<letter>`
- **Seed:** `ocp4-seed-<site>-<zone>`
- **KubeVirt cluster:** `ocp4-kubevirt-<site>-<zone>…`
- **Hosted cluster file:** `ocp4-<env>-<name>-<site>[-<x>].yaml`. The file stem is the segments-manager `cluster_name` and the day2 folder/Argo cluster name. The HostedCluster is `openshift-<cn>` in `hcp-<cn>`.
- **Cluster names** are unique across the whole estate.
- **Workflow ids are deterministic:** `allocate-segment-HC-<cluster>`, `create-hosted-cluster-<cluster>`, slot runs `<wf>-<mce>_<pool>_<n>`.
- **Task queues:** `<workflow>-workflow` for workflows; `<domain>-activity` for activities, with `-<mce>` added when the worker writes to an MCE.
- **Segments:** /24 only; types `HC`, `MCE`, `INVENTORY` (an MCE's BMH boot network), `PXE`, `HUB`, `UPI`. Only UPI segments can be shared (`cluster_name` is a list).
- **server-scan hostname rules:**
  - `^ocp4-hypershift[-data]` and `^ocp-<vendor>-<model>-<site>-<N>c-<M>gb…-<serial>` → HOSTED_CLUSTER
  - names containing `mce` → MCE
  - everything else → UPI
  - Only hostnames matching `^ocp` are ingested. Server `name` is not unique; identity is `vendor` + `serial`.
- **server-scan states:**
  - `openshift.lifecycle_state`: an Agent that is bound becomes `INSTALLED` with `cluster_name`/`mce_name`; an unbound Agent becomes `INSTALLED_TO_INVENTORY`.
  - Health: HEALTHY, WARNING, MAJOR, CRITICAL, UNKNOWN (UNKNOWN means "not read").

## Live sandbox

| Service | URL | What's there |
|---|---|---|
| segments-manager | <sandbox URL, see CLAUDE.local.md> | Sites site1/2/3, 50 /24s, one allocated (INVENTORY for `ocp4-mce-workflow-test`) |
| server-scan | <sandbox URL, see CLAUDE.local.md> | A seeded **fake** fleet (only the fake collector runs, no nodes-status jobs). **Auth disabled: every caller is the `dev` ADMIN** |
| workflows docs | <sandbox URL, see CLAUDE.local.md> | Docs site |
| orchestrator API | <sandbox URL, see CLAUDE.local.md> | Live; only upgrade-cluster has ever run. No auth |

We used only GET requests against these. We skipped server-scan `/servers/available` on purpose, because it queries the vendor manager and writes the result back.

## Sources

| Repo (`git@github.com:team-redbull/…`) | Commit read | Date | Detailed notes |
|---|---|---|---|
| server-scan | `f140914` | 2026-11-05 | [notes/server-scan.md](notes/server-scan.md) |
| segments-manager | `a4edc12` | 2026-10-11 | [notes/segments-manager.md](notes/segments-manager.md) |
| workflows | `00b3324` | 2026-11-05 | [notes/workflows.md](notes/workflows.md), [notes/workflows-orchestrator-openapi.json](notes/workflows-orchestrator-openapi.json) |
| herzi | `0ef4d2a` | 2026-11-07 | [notes/hosted-clusters.md](notes/hosted-clusters.md) |
| helm-charts-hostedclusters-setup | `1820ce0` | 2026-10-31 | [notes/hosted-clusters.md](notes/hosted-clusters.md) |
| gitops-day2-prod | `979e306` | 2026-09-29 | [notes/day2-kubevirt.md](notes/day2-kubevirt.md) |
| kubevirt-workflows | `f7b714e` | 2026-10-22 | [notes/day2-kubevirt.md](notes/day2-kubevirt.md) |
| gitops-day1-platform-config (GitHub mirror of the day1 values repo) | `d6e43de` | 2026-11-01 | This README |
| gitops-day1-argocd-platform (day1 ApplicationSets) | `07f31d3` | 2026-09-15 | This README |
| sim-day2-{argocd-day2-platform, sigs-falcon, sigs-lynx, sigs-orca, helm-charts, argo-appproject, day1-platform-config} (temporary day2 simulation, one repo per GitLab project) | 2026-09-29 | 2026-09-29 | This README |
| cluster-navigator | `710498c` | 2026-10-14 | [Vision](#vision-wingman-as-the-one-platform-later) |
| `~/Downloads/stack-export` (sanitized production export: chart, docs, ArgoCD platform) | n/a | — | [notes/hosted-clusters.md](notes/hosted-clusters.md) |
| Wingman itself | `47b0e02` | 2026-11-07 | [notes/wingman-today.md](notes/wingman-today.md) |

The file paths inside the notes are relative to those repos at those commits. The clones were shallow (`main` only), so the remote branches, including any in-progress Day1 workflow branch, were not checked. Secrets were never copied; where they exist, the notes say where.
