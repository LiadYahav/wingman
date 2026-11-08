# Notes: gitops-day2-prod + kubevirt-workflows, and what they mean for Wingman day2

Paths below are relative to:
- `ECO = a local clone of the team-redbull repos`
- `WM  = this repository`

No secrets were printed. Where they exist: the Argo scmProvider token secret `gitops-day2` (key `token`, namespace
`openshift-gitops` on prod-hub; referenced in `ECO/gitops-day2-prod/argocd-day2-platform/groups/templates/groupsAppset.yaml`);
the DHCP API token lives in the `helm-charts/dhcp-scope-manager` chart's `charts/dhcp-api-token/values.yaml` (referenced, not present);
`ECO/kubevirt-workflows/workflow/deploy/secret.example.yaml` is a placeholder template (GIT_TOKEN, ARGOCD_TOKEN), no real values.
GitLab host is redacted in the mock (`gitlab[REDACTED]`).

---

## 0. What these repos are

### gitops-day2-prod (mock of the air-gapped day2 GitOps setup)
- 4 commits, author itayherzberg, 2026-09-28..29. It's a **mock**: one checkout holds what in the air-gap are separate GitLab
  projects: `argocd-day2-platform/` (the machinery), `sigs/redbull/` (one team repo), `tools/` (harness, CI, guard rail). The day1
  repo is not checked in; the harness derives it.
- Real GitLab layout (from repoURLs in the templates):
  - `<top>/gitops-day2-prod/argocd-day2-platform.git`: 5 Helm charts that render only Argo Application/ApplicationSet objects
  - `<top>/gitops-day2-prod/sigs/<team>.git`: one repo per team ("sig"); **five sig repos in the air-gap** (ARCHITECTURE.md:279)
  - `<top>/gitops-day1/platform-config.git`: day1 repo, owns OCP versions (`mastertag`); day2 reads it and never writes it
  - `<top>/helm-charts/<chart>.git`: workload charts, one repo each, **one frozen branch per release**
  - In the mock `<top>` is `redbull`. `APPLY-RENAME.md` documents a planned rename of the `gitops-day2-prod` group (17 repoURL
    strings + 2 CI vars; sigs repos unaffected).
- Docs: `ARCHITECTURE.md` (team guide + runbooks R1–R11), `argocd-day2-platform/README.md` (template reference),
  `sigs/redbull/README.md` (the team-repo contract), `REFACTOR-PLAN.md` (design rationale), `CHANGES.md` (air-gap migration
  hand-off, Phases A–G), `APPLY-OCP-VERSIONS.md`, `APPLY-EXCLUSIONS.md` (F+G), `APPLY-UPI.md`, `APPLY-RENAME.md`.

### "redbull (not OCP)"
`ECO/kubevirt-workflows/docs/architecture.md` §8.1 names the actors:
- **RedBull Team (SRE / Platform Admin)**: "Operates the platform infrastructure. Creates and manages Seed Clusters, KV Clusters,
  and Customer MCE instances. Triggers platform-level operations ... via Temporal workflows and GitOps pipelines."
- **OCP Team**: "workload and OCP cluster optimisations ... Enables customer adoption of the GitOps-only model."

So `sigs/redbull` is the **RedBull infra/SRE team's sig repo**, not the OCP team's. It is **not** a non-OpenShift platform: every
destination in it is OpenShift (`ocp4-*` names, OCP `mastertag`s; UPI = OpenShift User-Provisioned Infrastructure). The redbull sig
holds infra charts: `bmhgen`, `kyverno`, `cluster-roles`, `dhcp-api-token` (MCE fleet default), and on prod-hub (`defaults/hub/`)
the DHCP scope manager, segments-manager and segment-lifecycle-worker (see the comment in `deploy/templates/deployApp.yaml`:
"siteNetworks: segments-manager and segment-lifecycle-worker must agree on the site list"; `defaults/hub/README.md`: "planned DHCP
tenant lands at `defaults/hub/dhcp-scope-manager/`"). The OCP team's sig would be a sibling repo `sigs/<ocp-team>` with the same
structure. All five sig repos render through the same platform charts. OCP and other clusters differ by **destination kind**, not
by sig:

| Destination | Argo that deploys it | Version source | Folder |
|---|---|---|---|
| prod-hub | prod-hub `openshift-gitops` | none (version-less) | `defaults/hub/<chart>/` |
| MCE hub ("in-cluster") | the MCE's own Argo | day1 `sites/<site>/mces/<mce>/version.yaml` (hand-maintained) | `sites/<site>/<env>/mces/<mce>/in-cluster/<chart>/` |
| hosted cluster | the MCE's Argo | day1 `sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml` | `sites/<site>/<env>/mces/<mce>/<cluster>/<chart>/` |
| UPI cluster (standalone OCP, no MCE) | second Argo on prod-hub, `openshift-gitops-upi` | optional `version.yaml` in the sigs folder | `sites/<site>/<env>/upi/<cluster>/<chart>/` |

### kubevirt-workflows
Mostly a **design repo** for the "70 :: OCP Kubevirt" platform, plus an early prototype:
- `docs/architecture.md`: arc42-style doc. Requirements R1–R4, quality goals, constraints C1–C7, ADs AD1–AD21, risks, glossary.
- `docs/procedures/00..18`: 18 procedures by layer (inventory, tenant clusters, KV clusters, seeds/hubs, upgrades, migration).
- `docs/inventory-controller.md`: per-hub reconciliation controller (design; thresholds "Still to decide").
- `docs/animations/*.html`: step-through animations, one per procedure.
- `docs/GAPS.md`: stale gap analysis (older numbering).
- `workflow/`: **implemented prototype**, Python `temporalio` `NodePoolManagerWorkflow` (scale signal → spread over 3 zones →
  git commit+push to the configured branch (main) → ArgoCD sync → wait healthy). The repo's own history has ~13 "scale OCP-A → total=N"
  commits made by it. `nodepools/OCP-A/zone-{1,2,3}.yaml` + `argocd/ocp-a.yaml` are synthetic demo manifests (ArgoCD app points at a
  github repo; the worker image comes from a Red Hat workshop cluster registry). `workflow/PLAN.md` (Go, delta signals, parent/child
  replenishment) and `workflow/workflows/provision_workflow.md` (parent fan-out) are **superseded**.
- Latest commit f7b714e (2026-10-22): "Rework inventory around the shipped slot model, not a parent workflow": "The team's workflows
  repo added install-server/bulk on 2026-10-20 ... Adopt it and drop the design that predated it." So the real implementations of
  the server-lifecycle/segment-lifecycle workflows live in the **workflows** repo; this repo documents and designs around them.

---

## 1. gitops-day2-prod in detail

### 1.1 The chain (app-of-apps via ApplicationSets)
Five platform charts, each rendering the next (`argocd-day2-platform/README.md` §3):

| # | Template | Runs on | Generator | Emits |
|---|---|---|---|---|
| 1 | `groups/templates/groupsAppset.yaml` | prod-hub | **scmProvider** over GitLab group id `243709` (= the sigs group) | App `<team>` → `mces` chart (`group: <repo name>`) |
| 2 | `mces/templates/mcesAppset.yaml` | prod-hub | git **directories** `sites/*/*/mces/*` | App `<team>-<mce>`, destination = the MCE → `clusters` chart + `$day1` valueFile `sites/<site>/mces/<mce>/version.yaml` |
| 3 | `mces/templates/appProjectAppset.yaml` | prod-hub | `clusters: {}` | AppProject `<team>` on every registered cluster (external chart `helm-charts/argo-appproject`) |
| 4 | `mces/templates/inClusterAppset.yaml` | prod-hub | dirs `defaults/hub/*` | `<team>-in-cluster-<chart>` → `deploy` in hub mode |
| 5 | `clusters/templates/clustersAppset.yaml` | the MCE | dirs `<mcePath>/*` minus `<mcePath>/in-cluster` | `<team>-<cluster>` → `operators` + `$day1` `hostedClusters/<cluster>.yaml` + `$values` `defaults/hosted-clusters/exclusions.yaml` |
| 6 | `clusters/templates/inClusterApp.yaml` | the MCE | static | `<team>-in-cluster` → `operators` with `cluster: in-cluster` |
| 7 | `operators/templates/operators.yaml` | MCE (UPI Argo for UPI) | dirs `<clusterPath>/*` + one of `defaults/mces/*`, `defaults/upi/*`, `defaults/hosted-clusters/*` (with `exclude:` from exclusions) | `<team>-<cluster>-<chart>` → `deploy` |
| 8 | `deploy/templates/deployApp.yaml` | MCE / prod-hub / UPI Argo | — | **leaf** `<team>-<cluster>-<chart>-deploy`, source = `repourl`@`targetRevision`/`path`, `releaseName: <chart>`, destination `name: <cluster>` |
| 9 | `mces/templates/upiAppset.yaml` | prod-hub | dirs `sites/*/*/upi/*` | `<team>-<cluster>` wrapper writing `operators` into ns `openshift-gitops-upi` |
| 10 | `mces/templates/upiAppProjectApp.yaml` | prod-hub | static | AppProject `<team>` in `openshift-gitops-upi` |

Key properties (ARCHITECTURE.md §1.1, §2, §6):
- **The folder is the registration.** No registry file, no marker file, no UI step: "creating a folder in your team's repo is how you
  deploy something". `.gitkeep` needed for an otherwise-empty cluster/MCE folder.
- **Folder basename == Argo cluster name == day1 file name** (join key). App names use basenames only, so `git mv` = in-place update.
- env/site never written in a file; read from the path (`path[1]`=site, `path[2]`=env). env ∈ {prod, prep, test}.
- Naming `ocp4-<env>-<name>-<site>[-<seq>]` (UPI exempt).
- Platform layers `selfHeal: true, prune: false`; **no resources-finalizer** → deleting a folder deletes the Application CR and
  **orphans** workloads (keeps running). **Leaf apps are manual-sync by default** (unless the chart's own `syncPolicy` opts in;
  only `dhcp-api-token` does).
- Labels on every generated app: `day2.gitops/{team,env,site,mce,cluster,chart,ocp-version,role}` → fleet ops by selector.
  Labels are per-Argo (leaves for hosted clusters sit on the MCE's Argo, ns `gitops-<team>`; UPI leaves on `openshift-gitops-upi`).
- THE ONE INVARIANT: each MCE/cluster/chart emitted by exactly one generator entry. **XOR rule**: a chart lives in a defaults
  folder OR a specific cluster folder, never both (duplicate app names), unless the cluster is excluded via `exclusions.yaml`.
- Frozen line `namespace: gitops-{{ .Values.repository }}`: never touch.

### 1.2 Team repo layout (`sigs/<team>/`)
```
sites/<site>/values.yaml                       # optional site slot
sites/<site>/<env>/values.yaml                 # optional site+env slot
sites/<site>/<env>/mces/<mce>/values.yaml      # MCE-wide slot
sites/<site>/<env>/mces/<mce>/in-cluster/<chart>/{<chart>.yaml,values.yaml}   # charts on the MCE hub
sites/<site>/<env>/mces/<mce>/<cluster>/values.yaml                            # cluster-wide slot
sites/<site>/<env>/mces/<mce>/<cluster>/<chart>/{<chart>.yaml,values.yaml}     # chart on hosted cluster
sites/<site>/<env>/upi/values.yaml
sites/<site>/<env>/upi/<cluster>/{version.yaml,values.yaml,<chart>/...}
operators/<chart>/{<chart>.yaml,values.yaml}                                   # team-wide defaults (never scanned)
operators/<chart>/ocp-versions/<v>/{<chart>.yaml,values.yaml}                  # <v> = FULL version e.g. 4.16.27
defaults/hub/<chart>/                       # → prod-hub
defaults/mces/<chart>/  + exclusions.yaml   # → every MCE hub
defaults/hosted-clusters/<chart>/ + exclusions.yaml
defaults/upi/<chart>/ + exclusions.yaml
```
Mock content: MCEs `ocp4-prep-mce-site1-a` (hosted `ocp4-prep-eyal-site1`, `ocp4-prep-itay-site1`) and `ocp4-prod-mce-site1-a`
(hosted `ocp4-prod-herzi-site1`, `ocp4-prod-karniol-site1`), UPI `ocp4-dok-site1`; operators `bmhgen`, `cluster-roles`, `kyverno`;
`defaults/mces/dhcp-api-token` (excluded from `ocp4-prep-mce-site1-a`).

Chart folder = two files:
- `<chart>.yaml` **deploy config**, read by the platform: `repourl` (**all lowercase**; `repoUrl` renders an empty repoURL, a known
  bug in several existing files, deliberately not fixed), `targetRevision` (default `HEAD`), `path` (default `.`),
  `projectNamespace`, `syncPolicy`, `ignoreDifferences`, `appname`, `oldConvention`.
- `values.yaml` **workload values**, passed to the chart.

### 1.3 Value stacks (every layer optional, `ignoreMissingValueFiles: true`, "slots")
Deploy config, lowest → highest (hosted cluster): `operators/<c>/<c>.yaml` → `operators/<c>/ocp-versions/<v>/<c>.yaml` →
`defaults/hosted-clusters/<c>/<c>.yaml` → `<clusterPath>/<c>/<c>.yaml`.

Workload values, lowest → highest (hosted cluster, 10 layers; `deploy/templates/deployApp.yaml`):
1 `operators/<c>/values.yaml` · 2 `operators/<c>/ocp-versions/<v>/values.yaml` · 3 `sites/<site>/values.yaml` ·
4 `sites/<site>/<env>/values.yaml` · 5 `defaults/hosted-clusters/<c>/values.yaml` · 6 `.../values-<env>.yaml` ·
7 `.../values-<cluster>.yaml` · 8 `<mcePath>/values.yaml` · 9 `<clusterPath>/values.yaml` · 10 `<clusterPath>/<c>/values.yaml`.
MCE in-cluster uses `defaults/mces/...values-<mce>.yaml`; UPI uses `defaults/upi/...` and `sites/<site>/<env>/upi/values.yaml` at 8.
Hub: `defaults/hub/values.yaml` → `operators/<c>/values.yaml` → `defaults/hub/<c>/values.yaml`.

Footguns: a `targetRevision` in a defaults config **overrides** ocp-version pins; ocp-versions layers are keyed by the **full** patch
version, so every upgrade (z-stream too) needs `ocp-versions/<new>/` created **before** day1 flips `mastertag`, otherwise pinned charts
silently fall back to the team default.

### 1.4 Versioning
- **Cluster OCP version**: owned by day1 `mastertag` (e.g. `4.16.27-x86_64` → ocpVersion `4.16.27`). Hosted cluster:
  `gitops-day1/platform-config/sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml` (day1's own provisioning input, which also
  carries e.g. `dhcp_values`, inert for day2). MCE: `.../sites/<site>/mces/<mce>/version.yaml` (day2-owned, `mastertag` only,
  hand-maintained). The day1 tree has **no `<env>` level**. A missing day1 entry is a loud render failure (`required`).
  UPI: optional `sites/<site>/<env>/upi/<cluster>/version.yaml` in the sigs repo.
- **Chart version**: pins are branch names in the chart repo (frozen branches; fixes are new branches like `2.1.5-hotfix`).
  Three pin levels: team default `operators/<c>/<c>.yaml` → per-OCP-version `operators/<c>/ocp-versions/<v>/<c>.yaml` (the normal
  fleet op) → per-cluster emergency pin `<clusterPath>/<c>/<c>.yaml`. Most charts track `main` and have no `ocp-versions/`.

### 1.5 Phases, tools/, UPI
From `CHANGES.md` header and status table (lines 1–70, 255–266):
- §0: background. The **Phase B production incident**: a `files:` generator with `config.yaml` at two depths matched hosted
  clusters as MCEs (git pathspec `*` crosses `/`), producing phantom apps. Hence discovery uses only `directories:` now.
- **A**: add marker files `mce.yaml`/`hc.yaml` (scaffolding). **B**: platform MR (generators, parametric paths, labels).
  **C**: move trees from legacy `mces/<mce>/<cluster>/` to `sites/<site>/<env>/mces/<mce>/<cluster>/` (one commit per team/MCE).
  **C'**: defaults renames (`in-cluster/`→`defaults/hub/`, `mces/in-cluster-defaults/`→`defaults/mces/`) + new
  `defaults/hosted-clusters/`. **D**: skipped. **E**: versions from day1, markers deleted (2026-08-17).
- Version-layer rename (2026-08-30): `operators/<c>/versions/ocp-<v>/` → `operators/<c>/ocp-versions/<v>/` (`APPLY-OCP-VERSIONS.md`).
- **F**: `defaults/<scope>/exclusions.yaml`, the structural opt-out. **G**: every check in CI (`tools/ci/*.gitlab-ci.yml`,
  blocking `lint`, informational `review`/`compare`). Standalone guide `APPLY-EXCLUSIONS.md`.
- **UPI** (2026-09-28): additive fourth destination kind (`APPLY-UPI.md`). The latest commit 979e306 is "docs: APPLY-UPI.md for a
  platform **without Phase F and without tools/**", and the doc says that is **"the air-gap's state"** (APPLY-UPI.md:52–59). Previous
  version for a Phase-F platform: `git show 32b36c6:APPLY-UPI.md`.
- `tools/`: `render-verify/render_chain.py` (909 lines, offline simulation of the whole chain: `snapshot`/`compare`, lints for day1
  parity, duplicates, exclusions, env allow-list, frozen line, depth-ambiguous globs); `ci/` (reference GitLab CI for sigs and platform
  MRs, not verified end to end); `migration-guardrail/` (temporary ClusterRole so Argo may delete Applications but not workloads
  during Phase C→E); `verify-phase-a.sh`.

**Inferred air-gap state (confirm with the team):** 2026-08-20 it was at the legacy pre-Phase-A layout (`mces/<mce>/<cluster>/`,
exactly what Wingman assumes); by 2026-09-29 it had reached A→E + the `ocp-versions` rename, **without** F (no `exclusions.yaml`) and
**without** `tools/` (no render harness/CI gate). UPI was being prepared to apply.

### 1.6 Exactly what a portal writes to install chart X on cluster Y
Hosted cluster `ocp4-prod-herzi-site1` (MCE `ocp4-prod-mce-site1-a`, site `site1`, env `prod`), team `redbull`, chart `cert-manager`.
One MR on `<top>/gitops-day2-prod/sigs/redbull`, adding:
```
sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1/cert-manager/cert-manager.yaml
sites/site1/prod/mces/ocp4-prod-mce-site1-a/ocp4-prod-herzi-site1/cert-manager/values.yaml
```
```yaml
# cert-manager.yaml: deploy config. If operators/cert-manager/cert-manager.yaml exists, only overrides belong here
# (an empty `{}` is fine). Otherwise it must carry repourl etc.
repourl: https://<gitlab>/<top>/helm-charts/cert-manager.git   # lowercase key!
projectNamespace: cert-manager
# targetRevision: "1.14.2"   # ONLY as a per-cluster emergency pin; omit to follow team default / ocp-versions/<v> pins
syncPolicy:
  syncOptions: [CreateNamespace=true]
  # automated: {selfHeal: true}   # leaf apps are manual-sync unless the chart opts in
```
```yaml
# values.yaml: layer 10 of 10, always wins
replicaCount: 2
```
Effect after merge: on the MCE's Argo (ns `gitops-redbull`) `redbull-ocp4-prod-herzi-site1-cert-manager` and its leaf
`redbull-ocp4-prod-herzi-site1-cert-manager-deploy` (destination `ocp4-prod-herzi-site1`, releaseName `cert-manager`) appear;
**nothing syncs** until someone runs `argocd app sync redbull-ocp4-prod-herzi-site1-cert-manager-deploy` (or by label).
Preconditions: cluster registered on the MCE's Argo under exactly that name; day1 file
`sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/ocp4-prod-herzi-site1.yaml` with `mastertag`; chart NOT already in
`defaults/hosted-clusters/` (XOR); if `ocp-versions/<v>/` pins exist for this cluster's version they apply unless overridden.

Other targets:
- MCE hub: `sites/<site>/<env>/mces/<mce>/in-cluster/<chart>/` (XOR with `defaults/mces/<chart>/`)
- UPI: `sites/<site>/<env>/upi/<cluster>/<chart>/` (XOR with `defaults/upi/<chart>/`)
- prod-hub: `defaults/hub/<chart>/`
- whole fleet: `defaults/hosted-clusters/<chart>/` (+ `values-<env>.yaml`, `values-<cluster>.yaml`); per-cluster tweak of a fleet
  default = `defaults/hosted-clusters/<chart>/values-<cluster>.yaml`, not a cluster folder
- opt-out (Phase F only): `defaults/hosted-clusters/exclusions.yaml` → `exclusions: {<chart>: [<cluster>]}`
- upgrade chart for one OCP version: `operators/<c>/ocp-versions/<v>/<c>.yaml` → `targetRevision: "<branch>"`
- remove: delete the chart folder. **Orphans** the workload. True teardown: `argocd app delete <...>-deploy --cascade` after the
  wrapper is gone (R8/R10). UPI also leaves `<team>-<cluster>-operators` ApplicationSet behind (APPLY-UPI.md §8).

---

## 2. Wingman day2 vs gitops-day2-prod: concrete mismatches

Wingman day2 code: `WM/apps/day2-service/src/{config.py,services/addon_service.py,routers/addons.py,services/approval_service.py,
services/helm_values_fetcher.py}`, `WM/packages/shared-python/src/wingman_shared/{path_resolver.py,models.py,mr_conventions.py}`.

What matches:
- Teams = GitLab projects in a sigs group (`DAY2_SIGS_GROUP_PATH`, `GitLabGroupClient.list_project_paths()`), the same model as the
  scmProvider (`$CI_PROJECT_NAME` IS the team name). Set it to `<top>/gitops-day2-prod/sigs`.
- Catalog = `operators/<addon>/` with `<addon>.yaml` + `values.yaml` (`DAY2_ADDON_DEFS_PATH_TEMPLATE="operators/{addon}"`) is right.
- Chart versions = branches of the chart repo (`HelmValuesFetcher.list_versions`), consistent with frozen-branch pins.
- Per-cluster install = two files in a chart folder via MR, consistent with runbook R4.
- `AddonArgoMetadata.repourl` reads lowercase `repourl`, same key as the platform.

Mismatches:
1. **Repo path is the legacy layout.** `DAY2_ADDON_OVERRIDES_PATH_TEMPLATE="mces/{mce}/{cluster}/{addon}"` (config.py:37) is the
   pre-Phase-C layout (REFACTOR-PLAN.md §3.1). Now: `sites/{site}/{env}/mces/{mce}/{cluster}/{addon}`. PathResolver has no
   `{site}`/`{env}` for day2 and `day2_mces_root()` assumes a top-level `mces/`. `list_all_clusters()` walks `mces/*/*` → finds nothing,
   and in the old layout would also list `in-cluster` as a "cluster".
2. **Only one destination kind.** Every cluster endpoint requires `mce` (routers/addons.py). No MCE in-cluster (`in-cluster/`),
   no UPI (no MCE at all), no prod-hub (`defaults/hub/`).
3. **No fleet layers / XOR awareness.** Wingman ignores `defaults/{hub,mces,hosted-clusters,upi}/` and `exclusions.yaml`. "Installed
   addons" for a cluster under-reports (fleet defaults are installed too), and installing a chart that is already a fleet default
   creates a duplicate app name (CI lint fails if Phase G exists; otherwise a real conflict). In the air-gap (no Phase F), a per-cluster
   override of a fleet chart must be `values-<cluster>.yaml` in the defaults folder.
4. **Values merge is 3 layers, real stack is 10.** `get_merged_addon_values` merges chart values → `operators/<c>/values.yaml` →
   cluster override. Missing: `ocp-versions/<v>/`, site, site+env, defaults (+env/+cluster), MCE-wide, cluster-wide.
5. **Version model ignores OCP-version pins.** "Team default version" = `operators/<c>/<c>.yaml` `targetRevision`, else first branch,
   else `"main"`. Real default is `HEAD`, and the effective version for a cluster may come from `operators/<c>/ocp-versions/<v>/<c>.yaml`
   keyed by the cluster's day1 `mastertag` (Wingman knows nothing about `mastertag`; grep finds no use anywhere in WM). Wingman writes
   `targetRevision` into the cluster folder whenever the chosen version differs from its idea of the default: in the new model that
   is an **emergency pin** that permanently detaches the cluster from fleet/version upgrades.
6. **`path` ignored.** HelmValuesFetcher reads `values.yaml` at the chart repo root; deploy configs may set `path` (e.g.
   `dhcp-api-token` uses `path: charts/dhcp-api-token`).
7. **`dependencies:` convention.** Wingman pops a `dependencies` key out of `operators/<c>/values.yaml` (addon_service.py:141). That
   file is passed verbatim to Helm by the platform, so the key would become a chart value. There is no dependency concept in day2.
8. **Remove ≠ uninstall.** Wingman's remove deletes the two files. In day2 that deletes the Application and **orphans the running
   workload**. Leaf apps are manual-sync, so **install doesn't deploy** either until someone syncs. Wingman has no Argo integration
   (sync/status/health per `day2.gitops/*` label or app name `<team>-<cluster>-<chart>-deploy`, which sits on the MCE's Argo).
9. **Cluster identity/env.** Wingman needs `site` and `env` to build paths: site from day1 path, env from the cluster name
   (`ocp4-<env>-<name>-<site>`) or by locating the existing MCE folder under `sites/*/*/mces/<mce>` in each sig repo. Creating a
   cluster folder in a sig that doesn't have it registers the cluster for that team (fine if the cluster is registered on the MCE's
   Argo and has a day1 file).
10. **No pre-merge verification.** The platform's rule is "Verify before merge: IDENTITY OK or it doesn't ship". Wingman's MRs
    should surface the CI `lint`/`review` results (`tools/ci/sigs-mr.gitlab-ci.yml`) where present, or run an equivalent check.
11. **MR conventions.** Day2 itself has no title/branch convention, so Wingman's `platform/{user}/{action}-{resource}-{ts}` and
    `[Wingman/Day2] ...` are free to keep. But `bulk_install_addons` uses `"[Day2] Install ..."` titles (addon_service.py:618–620),
    which break Wingman's own parseable convention. The ecosystem uses `[skip ci]` on workflow commits so a push doesn't restart the
    pipeline that called the workflow (kubevirt animations step "Commit manifests").
12. **Sync GitLab calls on the event loop**: `gl.commit_files`, `gl.create_mr`, `gl.file_exists` in addon_service.py violate the
    project's own async rule.
13. **Group rename planned**: keep every GitLab path configurable (APPLY-RENAME.md).

---

## 3. kubevirt-workflows in detail

### 3.1 Platform model (docs/architecture.md, deployment-view.png)
- Per AZ (3 zones): a **Seed** BM cluster (UPI-installed, MCE+HyperShift) hosting the **control planes of KV clusters** (AD17, AD18).
- **KV cluster** = a HyperShift hosted cluster whose BM workers run OpenShift Virtualization; scoped to one AZ (AD8). A "cell" = one
  KV cluster + its Seed resources + MCE inventory pool.
- **Customer MCE** = tenant hub, UPI on KubeVirt VMs, 3 masters (one per zone), one per **OCP version band** (diagram: MCE 4.18 serving
  HC 4.15→4.19; MCE 4.22 serving HC 4.19→4.23).
- **Tenant hosted cluster**: HCP on the Customer MCE, Agent platform (AD3; C2 explains why not KubeVirt platform), workers are KubeVirt
  VMs exposed as BMCs via kubevirt-redfish-controller, one NodePool per zone per node type.
- **InfraEnv per `<node-type>-<zone>`** (AD21), shared by all tenants on a hub = a **pool**. Warm pools of pre-registered Agents (AD14).
- **Temporal** for imperative orchestration that "exclusively mutat[es] the declarative SSOT (GitOps), maintaining ArgoCD as the sole
  state applicator" (AD13). Tenants are read-only, GitOps-only (AD5).
- **Server Scanner** = unified inventory/state tracker (AD15) = `server-scan`.
- No CPU/memory overcommit on KubeVirt (AD16).

### 3.2 Entities
Seed cluster, KV cluster, Customer MCE (hub), hosted cluster (tenant), NodePool, InfraEnv (pool), Agent, BMH, NMStateConfig, BMC
Secret, VirtualMachine, segment (INVENTORY per hub; HC per tenant cluster), DHCP scope, PXE map entry, node type (`32-128`,
`vm-32-128`), zone, version band, cell, watermarks.

### 3.3 The slot model and the inventory (docs/inventory-controller.md, procedures/01, 00)
- **Two loops that touch only through observed state** (procedures/README.md): demand (customer → Git → ArgoCD → NodePools on the hub)
  and supply (Inventory Controller → Temporal → Agents). "Nothing in the demand column waits for the supply column. A cluster can be
  created with no workers available."
- **Inventory Controller**: one per Customer MCE hub; every ~2 min per pool: `demand` = Σ NodePool replicas on this pool,
  `assigned`/`spare` from Agents (`spec.clusterDeploymentName` set or not), `running` = open Temporal runs
  `install-server-<infraenv>_*`. `low=max(minFree, lowPct×demand)`, `target=demand+low`, `ceiling=demand+high`,
  `needed = target − (assigned+spare+running)`; grow now, shrink only above ceiling after cooldown. Config in a ConfigMap
  (`lowPct/highPct/minFree/maxFree/cooldown`, per-pool overrides). Stateless, never in the tenant request path.
- **Slot model** (from the workflows repo, adopted 2026-10-22): one Temporal run per machine, ids `install-server-<infraenv>_<slot>`,
  slots walked from `_1`; `POST /workflows/server-lifecycle/install-server/bulk {infra_env, mce_cluster, count}` → 202 per-slot report
  (started / already_running / failed). **`count` is additive**: the caller must subtract running slots. In-flight is discoverable by
  asking Temporal, so there's no parent workflow. Dedup = one running workflow per id. Candidate headroom
  `candidate_count = min(20, busy + count + 2)`. Removal: `POST /workflows/server-lifecycle/remove-server` once per machine
  (`remove-server-<machine>` in the animation; procedures/02 header still says `remove-server-<infraenv>`, an inconsistency).
- Per-run add-server steps: resolve hub INVENTORY VLAN (segments worker) → draw candidates from server-scan → (VM pool, empty draw only)
  create VM on KV cluster → select bond NICs from `interfaces` (never `nic_macs`) → reserve (server-scan lock, CAS, keyed on workflow_id)
  → PXE map (IPMI only) → NMStateConfig → BMC Secret → BareMetalHost → await InfraEnv image (two conditions) → publish iPXE (IPMI)
  → await Agent → hold lock 24h. Ordered rollback (detach BMH before delete, clear only the metal3 finalizer).
- Workers / credentials: `segment-lifecycle-worker` (queue `segment-lifecycle-activity`, holds Segments Manager token, running);
  `server-lifecycle-worker` (queue `server-lifecycle-activity-<MCE_CLUSTER>`, **one per hub, inside it**, running); KubeVirt worker
  per KV cluster (planned). Workers dial out to Temporal; no cross-cluster kubeconfig anywhere.

### 3.4 User-facing flows (procedures)
| # | Procedure | Trigger | Workflow id | Writes |
|---|---|---|---|---|
| 01/02 | Add/Remove server to MCE | Inventory Controller | `install-server-<infraenv>_<slot>` / `remove-server-…` | hub k8s API directly (BMH, NMState, Secret), server-scan, PXE |
| 03 | Create hosted cluster | **Customer, "via the self-service catalog or a ticket"** | `create-hosted-cluster-<cluster>` | Segments Manager (allocate HC segment, verify) + **Git only** on `values_branch`; human merges; waits for control plane |
| 04 | Update NodePool | Customer | `update-nodepool-<cluster>-<node-type>` | Git only, absolute `desired_total` (≥3, spread over 3 zones) |
| 05 | Delete hosted cluster | Customer (`confirm: true`) | `delete-hosted-cluster-<cluster>` | drain → remove manifests in Git → human merge → await prune → agents unbind → scrub → delete DHCP scope → release segment |
| 06–09 | KV cluster create/add BM/remove BM/decommission | Operator / capacity policy | compositions of 03/04/01/02/05 with the Seed as hub | |
| 10–12 | Seed / add BM to Seed / Customer MCE | Operator | largely manual (UPI) | |
| 13/14 | Upgrade HC workers / control plane | Customer, own window | `upgrade-workers-<cluster>-<node-type>`, `upgrade-control-plane-<cluster>` | Git only (release image by digest) |
| 15–17 | Upgrade MCE hub / KV / Seed | Platform operator | `upgrade-hub-<hub>`, `upgrade-kv-<cluster>`, `upgrade-seed-<seed>` | skew check vs every HC; pauses the controller |
| 18 | Migrate version band | Tenant / hub retirement | `migrate-cluster-<cluster>` | 03 on new hub + 05 on old: a rebuild |

Procedure 03's commit (animation, `_generate.py` ~line 398) writes to the **day1 file**
`sites/<site>/mces/<hub>/hostedClusters/<cluster>.yaml` (`vlanId`, `dhcp_values`) plus HostedCluster and NodePools, with
`[skip ci]` in the message "or the push restarts the pipeline that called this workflow". So the workflow is expected to be
invoked from a pipeline/catalog, and it writes into the same day1 file Wingman day1 writes and day2 reads `mastertag` from.

### 3.5 The HTML files
`docs/animations/*.html` (15 files, generated by `_generate.py`): **step-through flow animations, not portal UI mockups.**
Self-contained inline SVG/JS for air-gapped viewing; arrow keys step, space plays, `#step=N` deep links; a BM/VM mode toggle where
steps differ. Each step shows actors (Customer/Operator/Controller, Temporal, Git, ArgoCD, server-scan, Segments Manager, DHCP API,
PXE, MCE hub, KV cluster, Seed) and the real call/payload/response/warning. The only "UI" concept is the box "Customer: catalog or
ticket" → Temporal. The 03 flow is: Customer → Temporal (request) → validate → Segments Manager allocate/verify → Git commit →
human merges → ArgoCD applies → await control plane → Inventory Controller fills pools.

### 3.6 Relation to the other repos
- **workflows** (Temporal + orchestrator API): hosts the shipped server-lifecycle workflows and the HTTP route
  `/workflows/server-lifecycle/install-server/bulk` and `/remove-server`, the slot model; RFC 9457 problem-document errors.
- **server-scan**: fleet inventory at `SERVER_SCAN_URL` (`/api/v1`): `GET /servers/available?pattern=^ocp-<infra_env>&count=N&health=HEALTHY`
  (live recheck, slow), `POST/DELETE /servers/{id}/reservation` (install lock, 409 with/without `held_by`). No "mark available" endpoint:
  a per-hub status job every 15 min. VM collector for KubeVirt: decided, not built.
- **segments-manager**: `GET /api/segments?type=INVENTORY` (no cluster filter, match client-side by `cluster_name`),
  `POST /api/segments/allocate {cluster_name, site, type: HC}`, `GET /api/segments/by-segment`, `POST /api/segments/release`.
  Deployed on prod-hub through **day2** (`defaults/hub` in the redbull sig, with segment-lifecycle-worker).
- **DHCP API** (dhcp-scope-manager chart; token deployed to every MCE by `defaults/mces/dhcp-api-token`): `/api/v1/scopes/<network>`;
  hostedclusters-setup's Crossplane Request reads the token (comment in `sigs/redbull/defaults/mces/dhcp-api-token/dhcp-api-token.yaml`).
  Today HC deletion = remove the chart, and a post-delete hook releases the segment (procedures/05).
- **herzi** (fills InfraEnvs on MCE clusters): not named in these repos. Functionally it overlaps the Inventory Controller / add-server
  (pool fill). A hosted cluster called `ocp4-prod-herzi-site1` exists in the day2 mock. Treat this link as inference.
- **helm-charts-hostedclusters-setup**: consumes the day1 `hostedClusters/<cluster>.yaml` (vlanId, dhcp_values) and the DHCP token.

---

## 4. How the team wants self-service portals to behave (quotes)

- Portal starts workflows, the workflow writes Git: procedures/03 "**Trigger** | Customer, via the self-service catalog or a ticket";
  "**Writes** | Git only. Nothing is applied to a cluster by this workflow." AD13: "Temporal guarantees transactional safety by
  exclusively mutating the declarative SSOT (GitOps), maintaining ArgoCD as the sole state applicator." architecture §8.2 Ticketing:
  "Requests flow from the ticket into the self-service catalog or directly to Temporal workflows."
- Human approval = merge to main: 03 "| 6 | — | human | **Merge to main.** ArgoCD only reads main." Open question 2: "Whether the
  merge to main stays manual. It is the only human step in the run".
- Absolute desired state, not deltas: README "**Absolute, never deltas.** Every count that crosses a boundary is the desired total."
  04: "`desired_total` ... **Absolute total across all three zones**, never a delta."
- Idempotency via workflow ids: "**Workflow ids are the dedup key.** Stable per target, with the mutable value in the payload."
- Create-verify-never-overwrite: "An existing resource is success once its identity fields match, and a conflict for a human when
  they do not, so an operator's hand correction survives a re-run."
- Quotas/admission: **not built**. 03 §6 "Admission, which does not exist yet ... Before this is customer-facing it needs a pre-flight
  that either rejects the request with a capacity reason or accepts it with an honest estimate." 04 gaps: "No capacity pre-flight",
  "No upper bound". architecture §4: "Pre-flight capacity checks ... routed to a different cell with headroom or rejected with capacity feedback."
- Portal must hide placement: architecture §4 Ease of Use "Self-service catalog exposes pre-packaged NodePool profiles abstracting
  Agent/Redfish complexity. AZ allocation and KV/MCE placement complexity is hidden from users". But 03 open question 1: "**Who picks
  the hub.** ... It is an input until something owns it."
- Async status, not "done": 03 ends at control plane available, "**Not** at workers ready"; 04 ends at "ArgoCD synced. **Not** at
  nodes ready." Progress is a Temporal query that names the queue ("that hub has no worker" vs "stuck").
- Tenant self-service upgrades with own window (13/14); platform upgrades are operator-only (15–17).
- Day2 itself: "There is no registration form and no UI step: creating a folder in your team's repo is how you deploy something"
  (ARCHITECTURE.md Part I). A portal in day2 is therefore an MR author over the folder contract, not a registry.

---

## 5. Integration points for Wingman

### 5.1 What Wingman day2 should become
A **GitOps MR author + Argo read model over the day2 folder contract**, not a store:
1. **Topology from the source of truth.** Discover destinations by listing directories, like the generators do:
   `sites/*/*/mces/*` (MCE), `<mce>/*` minus `in-cluster` (hosted), `sites/*/*/upi/*` (UPI), plus prod-hub. Join on basename with
   day1 `sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml` (and `version.yaml`) for `mastertag`. Union across all sig repos.
   Model `kind ∈ {hub, mce, hosted, upi}` + site/env/mce in the API instead of a required `mce` query param.
2. **Paths.** Replace the day2 templates with kind-aware builders: hosted `sites/{site}/{env}/mces/{mce}/{cluster}/{chart}`, mce
   `.../mces/{mce}/in-cluster/{chart}`, upi `sites/{site}/{env}/upi/{cluster}/{chart}`, hub `defaults/hub/{chart}`, fleet
   `defaults/{scope}/{chart}` and its `values-<env|cluster|mce>.yaml` siblings.
3. **Effective state = render the stacks.** Port the 10-layer workload stack and 4-layer deploy-config stack from
   `deploy/templates/deployApp.yaml` / `operators/templates/operators.yaml` (incl. `ocp-versions/<ocpVersion>` from day1 `mastertag`,
   `exclusions.yaml`), with provenance per layer. Show fleet-default charts as installed (source "defaults/hosted-clusters").
4. **Guard rails before opening an MR.** XOR check (refuse a cluster folder when the chart is a fleet default, unless excluded);
   lowercase `repourl`; env allow-list; no stray dirs; `.gitkeep` for empty clusters; warn when a per-cluster `targetRevision`
   becomes an emergency pin; warn on `targetRevision` in defaults configs. Run/require `render_chain.py snapshot/compare` (or show the
   sigs-MR CI `lint`/`review` result) and display APPS ADDED/DISAPPEARED. Note the air-gap may lack `tools/` and Phase F today.
5. **Version operations** as first-class MRs: per-OCP-version pins (`operators/<c>/ocp-versions/<v>/<c>.yaml`), team default, emergency
   pin. "Prepare OCP upgrade": list pinned charts in every sig that lack `ocp-versions/<new>/` before day1 flips `mastertag`
   (footgun §4.4-2). That's a cross-sig check only a portal can do easily.
6. **Argo integration** (read + sync): status by app name `<team>-<cluster>-<chart>-deploy` / labels `day2.gitops/*` on the right Argo
   (MCE Argo ns `gitops-<team>`; prod-hub; `openshift-gitops-upi`). A "Sync" action after merge, since leaves are manual-sync.
   "Remove" must offer orphan vs teardown (`--cascade` delete after the wrapper disappears).
7. Drop Wingman-only conventions that leak into Helm values (`dependencies:` in `operators/<c>/values.yaml`); read `path` from the
   deploy config when fetching chart values; default `targetRevision` = `HEAD`.
8. Keep MR conventions (branch/title parseable for audit), fix the bulk `[Day2]` titles, one MR per sig repo (bulk across teams =
   N MRs); make every GitLab path configurable (group rename planned).

### 5.2 Whether/how Wingman should expose kubevirt flows
- Yes, as the "**self-service catalog**" the architecture keeps referring to (03/04/05/13/14 are customer-triggered; 15–17 operator).
  Per the design, Wingman should **start Temporal workflows via the orchestrator API** (workflows repo) with stable workflow ids and
  absolute desired state, then **show progress via workflow queries**. It should not write HostedCluster/NodePool manifests to Git itself.
  The workflow commits to a `values_branch`; Wingman's existing approval UI (list/approve/merge MRs) can serve as the "human merges to
  main" step.
- Overlap to resolve with day1: procedure 03 writes the day1 file `sites/<site>/mces/<hub>/hostedClusters/<cluster>.yaml`
  (vlanId, dhcp_values) after allocating a segment, which is what Wingman day1 does by rendering specs. Either Wingman day1 becomes
  a caller of `create-hosted-cluster` (passing name, hub, release digest, worker_types per zone, values_branch, secret refs), or the
  workflow must accept Wingman's rendered spec. Decide one writer for that file.
- Day-2 actions on a hosted cluster in Wingman: "Scale worker type X to N" → `update-nodepool-<cluster>-<node-type>` (absolute total,
  ≥3); "Upgrade control plane / workers" (14 then 13; skew-gated by hub); "Delete cluster" (05, explicit confirm); "Migrate version
  band" (18). Operator-only views: pools per hub (demand/assigned/spare/running slots), hub skew, controller paused state.
- Gaps Wingman must not paper over: no admission/capacity pre-flight (show "may sit with zero workers"), hub placement has no owner
  (an input today), end-to-end time unpredictable while merge is manual.
- Inventory views can come from server-scan (`/servers/available`, reservations), Segments Manager (segments by hub/site/type) and
  Temporal (open `install-server-<infraenv>_*` runs), all read-only and with viewer tokens. Writes stay in workflows.
