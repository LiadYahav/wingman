# Hosted-cluster setup today: herzi, hostedclusters-setup chart, stack-export GitOps

Scope: how a hosted cluster gets set up in the new ecosystem, and what Wingman day1 should produce.
Paths: `ECO=a local clone of the team-redbull repos`,
`SE=~/Downloads/stack-export (local, private)`, `WM=this repository`.
Secrets, tokens, pull secrets and certificates are mentioned by location only.

---

## 0. Two environments, two copies of everything (read first)

| | Connected / sandbox (GitHub) | Air-gapped / production (GitLab) |
|---|---|---|
| Chart | `github.com/team-redbull/helm-charts-hostedclusters-setup` (`$ECO/helm-charts-hostedclusters-setup`) | `git.example.internal/internal/helm-charts/hostedclusters-setup.git` (`$SE/charts/hostedclusters-setup`) |
| Values repo | `team-redbull/day1` (GitHub) | `gitops-day1/platform-config` (GitLab, `$SE/gitops/platform-config`) |
| ApplicationSets | `argocd-platform` (connected shape) | `gitops-day1/argocd-platform` (`$SE/gitops/argocd-platform`) |
| HostedCluster/NodePool rendered? | Only with `hostedCluster.enabled: true` (off by default; ported 2026-10-31) | Always |
| Status | "Treat the GitLab chart as the one that builds production clusters" (`$ECO/helm-charts-hostedclusters-setup/README.md`, "Convergence") | Production |

Convergence is undecided: either the GitHub templates merge into GitLab (GitLab stays canonical) or GitLab mirrors GitHub. The second option has started (README "Convergence").
The repo layout, values layering and ApplicationSet cascade are the same in both. The differences that matter to a portal are in §3.4.

---

## 1. herzi: the InfraEnv capacity controller

Source: `$ECO/herzi` (Go, controller-runtime, Kubebuilder scaffold). Key docs: `README.md`, `CLAUDE.md`, `docs/design/herzi-design.md`, `docs/ops/operating.md`.

### 1.1 What it reconciles
- **It owns no CRD and has no status subresource.** It watches three external kinds as unstructured objects (`internal/kube/types.go`):
  - `InfraEnv` (`agent-install.openshift.io/v1beta1`): the **pool**. Reconcile key = InfraEnv name in one `agentNamespace` (default `inventory`).
  - `Agent` (`agent-install.openshift.io/v1beta1`): the **supply**, attributed by the label `infraenvs.agent-install.openshift.io=<infraEnv>`.
  - `NodePool` (`hypershift.openshift.io/v1beta1`): the **demand**. Only `platform.type: Agent`, attributed through `spec.platform.agent.agentLabelSelector.matchLabels["infraenvs.agent-install.openshift.io"]`.
- RBAC (`charts/herzi/files/rbac-rules.yaml`): get/list/watch on agents and nodepools; get/list/watch/**patch** on infraenvs (annotations only). There are no create or delete verbs.
- One controller per MCE hub, chosen by leader election. `MaxConcurrentReconciles` is 4, the default requeue interval is 60s, and a file watcher hot-reloads the config.
- **Every InfraEnv in `agentNamespace` is managed by default.** Two ways to opt one out: the label `herzi.redbull.io/ignore` (any value), or `pools.<name>.exclude: true` in config. Pause one with the annotation `herzi.redbull.io/paused: "true"` or `pools.<name>.paused`.

### 1.2 How it decides (the formula)
```
demand  = sum of NodePool.spec.replicas whose selector is ONLY {infraenvs.agent-install.openshift.io: <pool>}
supply  = assigned (bound Agents) + claimable (approved, connected, unbound) + settling (<60m) + open Temporal runs
buffer  = max(minFree=2, (highPct=10 * demand + 50)/100)
target  = demand + buffer;  need = target - supply
need > 0 -> POST add-server-to-mce {infra_env, mce_cluster, namespace, count<=20}, at most 15 open runs per pool
```
- **It is add-only.** Capacity is never reclaimed, and lowering demand only stops further additions.
- Failure handling: an empty inventory puts the pool in probe mode (1 machine every 20 min). Unknown or errored reads block the pool. Zero pollers on any of the 3 Temporal queues blocks ordering.
- **NodePool shape requirements**, a hard contract that Wingman's output must respect (`herzi-design.md`, Attribute stage):
  - The selector must be exactly one matchLabel, `infraenvs.agent-install.openshift.io`. Any extra label or matchExpression makes it a **pool problem that blocks the whole pool**.
  - `replicas` must be set. Autoscaling NodePools count as a "no replicas" problem.
  - Paused or deleting NodePools are not counted as demand.
- The chart's `nodepool.yaml` already renders exactly this shape, from `infraEnvName`.

### 1.3 Which servers go into which InfraEnv, and from where
- **herzi does not pick servers or BMHs.** It sends only a count per InfraEnv:
  `POST <installURL>/workflows/server-lifecycle/add-server-to-mce` with body `{"infra_env","mce_cluster","namespace","count"}` (`internal/installer/installer.go`, `testdata/request.json`).
- The **workflows** Temporal workflow `add-server-to-mce` then does the rest:
  - `acquire_servers` picks hardware from **server-scan**, which refreshes about every 15 min.
  - It resolves a VLAN through segment-lifecycle activities (the segment queue).
  - It installs the server, which registers as an Agent in that InfraEnv. Agents are auto-approved by the hub.
- herzi itself never calls server-scan or segments-manager. It only reads Kubernetes and Temporal (DescribeWorkflowExecution on fixed workflow IDs `add-server-to-mce-<mce>_<infraEnv>_<slot 1..100>`, plus DescribeTaskQueue).
- InfraEnv naming in the new workflows (`$ECO/workflows/shared/infraenv_names.py`):
  - `<conf>[-<opt>]-zone-<zone>-metal` for bare metal.
  - `<conf>[-<opt>]-zone-<zone>-<cpu>` for KubeVirt-VM agents, created by `create-vm`.
  - The export's production clusters still use older names such as `dell-r660-site-c-128c-1024gb-10tb` and `classic-baremetal-dell`.
- **Who creates the InfraEnv objects is not in any repo I read.** That is a gap (§4.3).

### 1.4 Status a portal can read
- **No CR status, no API.** These are the available surfaces:
  1. **Prometheus metrics** over HTTPS (`<release>-metrics` Service, TokenReview/SAR auth; bind a subject to ClusterRole `<release>-metrics-reader`). Per-pool gauges: `herzi_pool_demand/_assigned/_claimable/_settling/_stuck_agents/_open_runs/_target/_need`, `herzi_pool_blocked{reason}`, `herzi_pool_probe_mode` ("hardware missing"), `herzi_pool_failure_class{class}`, `herzi_last_successful_reconcile_timestamp_seconds`. Counters: `herzi_orders_total{mode,result}`, `herzi_machines_ordered_total`, `herzi_install_errors_total{kind}`. Also `herzi_config_valid`. Catalogue: `README.md` "Metrics".
  2. **InfraEnv annotations:** `herzi.redbull.io/state` (JSON, ≤1 KiB: `capFailAt`, `otherFails`, `lastOKAt`, `probeNotBefore`) and `herzi.redbull.io/blocked-until`.
  3. **Temporal and orchestrator runs:** `GET /workflows/runs` and `GET /workflows/runs/{id}` on the orchestrator API, filtered to `add-server-to-mce-<mce>_<pool>_*`.
  4. Logs (a pool status line, "Would install" in dry run) and PrometheusRule alerts (`charts/herzi/files/alerts.rules.yaml`).
- Backlog idea: an `InventoryPolicy` CRD with status (`herzi-design.md` §H). It does not exist yet.

### 1.5 Operational state that matters for "will my cluster get nodes?"
- **`dryRunGrow` defaults to true for every pool.** Going live is a manual, per-pool `dryRunGrow: false` in the herzi Helm values (`docs/ops/operating.md`).
- Release gates are still open: herzi has not run on a real hub, and Temporal/workflows connectivity has not been verified live (`operating.md` "Integration status").
- If a pool is still in dry run or blocked, a new cluster's NodePools wait for Agents that nobody orders.
- Helm values (`hack/chart/example-values.yaml`):
  - Required: `config.mceName` (canonical `ocp4-...`), `installURL`, `temporalAddress`, `image.repository`.
  - Per-pool overrides: `highPct`, `minFree`, `maxOpenRunsPerPool`, `probeInterval`, `drawGrace`, `failureMemory`, `settlingMax`, `dryRunGrow`, `paused`.

---

## 2. The hostedclusters-setup chart: values contract and rendered resources

### 2.1 How values arrive
The tier-3 ApplicationSet (`$SE/gitops/argocd-platform/hostedClusters/templates/hcAppset.yaml`) builds each cluster's values by layering files, last wins:
```
chart values.yaml
 -> $values/sites/configValues.yaml                       (global)
 -> $values/sites/<site>/values.yaml                      (site)
 -> $values/sites/<site>/mces/<mce>/values.yaml           (MCE)
 -> $values/sites/<site>/mces/<mce>/hostedClusters/<file> (the cluster)
+ helm parameter clusterName = file's clusterName, else filename minus .yaml minus "ocp4-"
```
- `ignoreMissingValueFiles: true` makes the site and MCE layers optional.
- Helm **replaces lists**; it does not append them. That is why `dhcp_values.dns.extraServers` exists alongside `dns.servers`.
- Connected copy difference: its hcAppset also passes `site` and `mce` as parameters (needed by the day2 Job). Its `clusterName` is expected to be the full `ocp4-<env>-<name>-<site>` (`values.yaml` comment, `_day2-helpers.tpl`; `APPLY-HC-DEFAULTS.md` §5.2/§12 warns about this).

### 2.2 Values contract

**Identity (never written by a portal into the file unless overriding)**
- `clusterName`: derived from the file name `ocp4-<clusterName>.yaml`. It names the HostedCluster `openshift-<clusterName>` in namespace `hcp-<clusterName>`, the control-plane namespace `hcp-<clusterName>-openshift-<clusterName>`, and the Argo Application (the full file stem).
- `site`, `mce`: from the directory path.

**Cluster file: what a human or portal writes** (`$SE/gitops/platform-config/README.md` "The cluster YAML"; `$SE/docs/APPLY-HC-DEFAULTS.md` §11)

| Key | Req? | Default / meaning |
|---|---|---|
| `owner: {merkaz, anaf, mador}` | yes (prod) | org-unit numbers, rendered into an owner ConfigMap (air-gap chart) |
| `mastertag` | **yes** | OCP release. `4.22.8` and `4.22.8-x86_64` are both accepted; a bare X.Y.Z gets `-x86_64` |
| `nodepool[]` | yes | see below |
| `platform` | no | Agent; write only `kubevirt` |
| `hostInventory` | no | `inventory`, the Agent namespace |
| `workertag` (top-level) | no | follows `mastertag`; written only during masters-first upgrades |
| `imageContentSources` | no | extra mirrors, merged with `defaultImageContentSources` unless `disableIdmsMerge: true` |
| `imagePath`, `imageHc` | usually MCE-level | release mirror base; control-plane images base |
| `allowDeletion` | no | HostedCluster label |
| `pausedUntil` | no | `"true"` or an RFC 3339 time; written by the upgrade workflow's abort |
| `upgrade: {profile, wave}` | no | read by the upgrade workflow (connected lab fixture) |
| `Network:` | legacy | firewall flows between segments; no current consumer found (the "Next" connectivity service is described as gone in `allocate_segments.py`) |
| `AutomateAllocation: "false"` + `vlanId` | rare | manual segment; CI then never allocates |
| `clusterName` | no | only when the file name differs from the cluster name. **Never rename a file**: that renames the cluster |

**Per nodepool**

| Key | Default |
|---|---|
| `infraEnvName` | **required on agent**. It is the value of label `infraenvs.agent-install.openshift.io`. Legacy form: `agentLabelSelector: {nodeLabelKey, nodeLabelValue}`; a disagreement fails the render |
| `name` | `<clusterName>-<infraEnvName>`. **Required** when two pools share an InfraEnv (zones) |
| `replicas` | 1 when the key is absent; an explicit `0` is honoured |
| `labels.allowDeletion` | "false". Always write `allowDeletion: false` |
| `labels.maxReplicas` / `minReplicas` | `replicas` / `replicas-1` |
| `configs[].name` | MachineConfig/KubeletConfig names. CI resolves them to `mc-files/` and renders them into `mcConfigMap` |
| `workertag` | top-level `workertag`, else `mastertag` |
| `nodeDrainTimeout` | `0s` |
| other optional fields | `nodeVolumeDetachTimeout`, `autoRepair` (false), `upgradeType` (InPlace), `inPlace.maxUnavailable`, `replace.{strategy,rollingUpdate.{maxSurge,maxUnavailable}}`, `nodeLabels{}`, `tuningConfig` (string or list) |
| KubeVirt only | `cores` (6), `memory` (12Gi), `qosClass`, `size` (32Gi root), `type`, `storageClass`, `vlan` (→ NAD `default/nad-<vlan>`, else top-level `vlanId`), `additionalNetwork`, `attachDefaultNetwork` |

**Written by automation, never by a human or portal**
- `vlanId` and `dhcp_values: {network: <x.y.z.0>}` (plus `exclusions`): appended by the orchestrator's `allocate-segment` workflow.
- `mcFiles`: defaults to the list of nodepool config names.
- `mcConfigMap[]`: written by CI under `# === Added by CI ===`. It is frozen once present.

**MCE / site / global layers** (`$SE/gitops/platform-config/sites/configValues.yaml`, `sites/<site>/values.yaml`, `sites/<site>/mces/<mce>/values.yaml`)

| Area | Keys |
|---|---|
| Release images | `imagePath` (per MCE), `releaseRepo` (`openshift/release-images`), `cpoRepo` (`openshift/release`, or `""` for none), `imageHc` |
| Registries and mirrors | `defaultImageContentSources`, `defaultImageRegistries`, `extraImageRegistries` |
| etcd and scheduler | `etcd.{size,storageClassName,type}` (8Gi / powerflex-sp1), `scheduler.config` |
| Availability and networking | `controllerAvailabilityPolicy`, `infrastructureAvailabilityPolicy` (HighlyAvailable), `networkType` (OVNKubernetes), `clusterNetworkCidr`, `serviceNetworkCidr` (connected only; hardcoded in air-gap), `olmCatalogPlacement` |
| DNS, certs, ingress | `baseDomain` (`""` lets HyperShift derive it), `dns.{site,zone}` and `certificate.{mceName,oauthSecretName,certName}` (air-gap DNS records and cert-manager Certificates), `serviceType` (NodePort, LoadBalancer, or default), `services` (verbatim publishing strategy), `loadbalancer.addresspool` (MetalLB, air-gap) |
| Feature switches | `disableProxy`, `disableCustomCa`, `disableAPIDNS`, `skipApiCert`, `skipApiConfig`, `disableLdap`, `disableOcpadmin`, `ldapUrl` |
| Secret names | `pullSecretName`, `sshKeySecretName`, `etcdEncryptionKeySecretName`, `additionalTrustBundleName`, `registriesTrustedCAName`, `infraKubeConfigSecretName`, `kubevirtInfra` (external or local) |
| Gates | `hostedCluster.enabled` (connected), `kyverno.enabled`, `namespace.labels` |
| DHCP globals | `dhcp_values.{dns.servers, dns.extraServers, dns.domain, failover{...}, leaseDurationDays, pxe}` |
| Day2 and segment release | `day2.copy_to_sigs` (list of sigs to register with) |
| Chart-only (base values) | `dhcp_api`, `crossplane`, `release_segment` |
| Air-gap only | `backup_schedule`, `loggingOperator`, `go_api`, `kubeconfigSync`, `Next`, `clusterType` |
| Argo app-level (tier-3 appset values) | `ignoreDifferences`, `syncPolicy`. Both are fed from configValues through the tier-2 Application |

No explicit ingress or API VIP value exists:
- The API is either a LoadBalancer Service (MetalLB pool `loadbalancer.addresspool`), a NodePort at `api.openshift-<cn>.<baseDomain>`, or HyperShift's default (LoadBalancer API plus Routes).
- DNS: Crossplane CNAMEs `api`, `api-int` and `avi-ingress` point at AKO/AVI (`<...>.<dns.site>.ako.<zone>`), and an apps wildcard is created through an HTTP DisposableRequest to an internal DNS service.

### 2.3 Rendered resources

**Connected chart** (`$ECO/helm-charts-hostedclusters-setup/templates`), with sync waves:
- `namespace.yaml`: `hcp-<cn>` and `hcp-<cn>-openshift-<cn>` (wave -1 when `namespace.labels` is set).
- `hc.yaml`: `HostedCluster openshift-<cn>` (wave 2). Covers release image, dns, etcd, platform agent/kubevirt, secretEncryption, networking, pullSecret ref, configuration (scheduler, proxy, operatorhub, apiServer certs, OAuth LDAP and htpasswd IdPs, image trust), sshKey ref, `kubeAPIServerDNSName`, and services.
- `nodepool-configmaps.yaml`: `mcConfigMap` and `tuningConfigmap` ConfigMaps (wave 3).
- `nodepool.yaml`: one NodePool per entry (wave 4).
- `capi-kyverno-policy.yaml`: needs `kyverno.enabled`.
- `dhcp-scope-request.yaml`: Crossplane `http.m.crossplane.io/v1alpha2 Request dhcp-scope-<network>`. provider-http calls dhcp-scope-manager's `/api/v1/scopes/<network>` (POST/GET/PUT/DELETE), which manages Windows DHCP. It is gated on `dhcp_values.network`.
- `add-cluster-to-day2-job.yaml` (wave 100, after everything is Healthy): a git push of `sigs/<sig>/sites/<site>/<env>/mces/<mce>/<cluster>/.gitkeep` into `github.com/team-redbull/gitops-day2-prod`, once per sig in `day2.copy_to_sigs`. `<env>` comes from field 2 of `ocp4-<env>-<name>-<site>`.
- `release-segment-hook.yaml`: an Argo **PostDelete** Job that POSTs `{cluster,type:HC}` to `<orchestrator>/workflows/segment-lifecycle/release-segment`. It is described as a bridge until a deprovision workflow exists.
- **It renders no Secret.** The pull secret, SSH key, etcd encryption key, LDAP bind password and htpasswd must pre-exist in `hcp-<cn>`.

**Air-gap chart** (`$SE/charts/hostedclusters-setup/templates`). Everything above except the day2 Job and the release hook, plus:
- cert-manager Certificates (`api-certificate`, `oauth-certificate`).
- Crossplane `CNAMERecord`s (`api-dns-record`, `avi-ingress-dns-record`) and a `DisposableRequest` for the apps wildcard DNS.
- `cluster-go` (a DisposableRequest registering a console shortcut).
- CA bundle and proxy ConfigMaps, the `custom-registries` ConfigMap, and the `ldap-ca` ConfigMap.
- Velero daily and hourly `Schedule`s.
- logging-operator `SyslogNGFlow` and `SyslogNGOutput`.
- The owner ConfigMap (in `hcp-generic`).
- A kubeconfig-sync `CronJob` (`job-o-script.yaml`).
- A MetalLB API `Service` when `serviceType: LoadBalancer`.
- An `infra-kubeconfig` Secret (KubeVirt).
- Secrets: `pull-secret.yaml`, `htpasswad-ocpadmin-secret.yaml`, `ldap-bind-password-secret.yaml`, `secret-ssh.yaml`, `secret-logging.yaml`.

### 2.4 Recent changes, connected chart (`git log`, newest first)
- 2026-10-31 `b73bfb4` **feat: render the HostedCluster and NodePools, behind `hostedCluster.enabled`.** This is the port from GitLab. The golden tests (`tests/golden/`) match the GitLab output over 51 cluster files and 99 NodePools. Keys added: `releaseRepo`, `cpoRepo`, `kubevirtInfra` (local VMs on the MCE), `baseDomain:""`, CIDRs, the secret-name keys, `disableLdap`, `services`, `pausedUntil`, `nodepool[].storageClass`.
- 2026-10-31 `1820ce0`: an empty `baseDomain` renders no `dns` block. A rendered empty field would stay OutOfSync forever and break the upgrade workflow's "nothing unexpected out of sync" check.
- 2026-10-10: release-segment PostDelete hook (retries for up to 55 min itself; Argo does not retry a failed PostDelete hook).
- 2026-09-15: register new hosted clusters with the day2 sig repos.
- 2026-08: DHCP scope integration (Crossplane v2 namespaced Request, bearer-token placeholder, `scopeName` derived from the upper-cased cluster name, per-site DNS servers).

**Air-gap side ("HC defaults", `$SE/docs/APPLY-HC-DEFAULTS.md`):** cluster files are slimmed by moving repeated values into defaults:
- `clusterName` from the file name, `platform` defaults to agent, `hostInventory` to `inventory`.
- `infraEnvName` replaces the 3-line `agentLabelSelector`.
- Labels are auto-quoted, and `workertag` follows `mastertag`.
- `mcFiles` defaults to the configs list; `nodeDrainTimeout` defaults to `0s`; `replicas: 0` is honoured.
- The appset passes `clusterName` with `trimPrefix "ocp4-"`, and `scripts/slim_hc_values.py` migrates existing files.
- Rollout is gated (steps a–d, one MR per MCE). The changes are already in the export mirror (`nodepool.yaml` has the `infraEnvName` guards).

### 2.5 Compact example: one cluster, as a portal should write it
From `APPLY-HC-DEFAULTS.md` (the slimmed `ocp4-test-storage-site-a-a.yaml`), owner numbers replaced with placeholders:
```yaml
# sites/site-a/mces/cluster-mce-site-a-prep/hostedClusters/ocp4-test-storage-site-a-a.yaml
owner: {merkaz: "<unit>", anaf: "<unit>", mador: "<unit>"}
mastertag: 4.22.8                       # -> 4.22.8-x86_64
nodepool:
- infraEnvName: dell-r660-site-a-128c-1024gb-5tb
  replicas: 2
  labels: {allowDeletion: false}
  configs:
  - name: nm-conf-test-storage-site-a-a-dell-data   # template nm-conf-template-dell-data.bu
  - name: worker-kubeletconfig-reserved
  - name: nic-ring-buffer
  - name: workers-chrony-configuration
- infraEnvName: kubevirt-site-a-32c-256gb
  replicas: 0
  labels: {allowDeletion: false}
  configs:
  - name: nm-conf-test-storage-site-a-a-kubevirt
  - name: worker-kubeletconfig-reserved
# ---- later appended to the SAME file on the MR branch, never by the portal ----
# vlanId: 4xx                         <- allocate-segment workflow
# dhcp_values: {network: 192.0.2.x}   <- allocate-segment workflow
# mcConfigMap: [...]                  <- CI ("# === Added by CI ===")
```
Older, fully explicit example: `$SE/gitops/platform-config/sites/site-a/mces/cluster-mce-site-a/hostedClusters/cluster-cicd-prod-2.yaml`. It has an explicit `clusterName`, `agentLabelSelector`, `'''4'''` labels, `vlanId`, `dhcp_values`, `Network:` flows and `mcConfigMap`.
Connected-lab example, KubeVirt local, which renders the HostedCluster: `$ECO/helm-charts-hostedclusters-setup/tests/fixtures/hostedcluster/lab-kubevirt-local.yaml`.

---

## 3. GitOps delivery path

### 3.1 Repos and hosting
- Production uses GitLab (`git.example.internal`):
  - `internal/gitops-day1/argocd-platform` (ApplicationSets).
  - `internal/gitops-day1/platform-config` (values repo with `.gitlab-ci.yml`).
  - `internal/helm-charts/hostedclusters-setup` (chart).
- The connected sandbox uses GitHub: `team-redbull/day1` (values) and `team-redbull/helm-charts-hostedclusters-setup`. The day2 registration Job targets `team-redbull/gitops-day2-prod` (GitHub).
- The workflows' `allocate-segment` pushes into whatever `day1_repo_url` points at (https + token; `$ECO/workflows/shared/settings.py`).

### 3.2 ApplicationSet cascade (`$SE/gitops/argocd-platform/*/templates`)
1. **Tier 1 `sites`** (hub Argo, `openshift-gitops`): git directories generator over `sites/*` produces one Application per site. That Application installs the `mces` chart with `site=<dir>`. Sync is automated with selfHeal, prune=false.
2. **Tier 2 `<site>-mces`**: directories generator over `sites/<site>/mces/*` produces one Application per MCE. That Application installs the `hostedClusters` chart (values: `configValues.yaml` plus `site`, `mce`) with **destination = the MCE cluster** (`destination.name: <mce dir>`). The tier-3 ApplicationSet therefore lands on **the MCE's own Argo CD**. Sync is automated with selfHeal, prune=false.
3. **Tier 3 `<mce>-hc`** (on the MCE's Argo): goTemplate files generator over `sites/<site>/mces/<mce>/hostedClusters/*`. It produces one multi-source Application per file:
   - The Application is named after the file stem.
   - Source 1 is the chart repo at `main`, with the 4 valueFiles and the `clusterName` parameter.
   - Source 2 is `ref: values`, platform-config at `main`.
   - Destination is in-cluster (the MCE), namespace `openshift-gitops`.
   - syncPolicy and ignoreDifferences come from values. **The exported `configValues.yaml` sets `ignoreDifferences` but no `syncPolicy`, so tier-3 Applications appear to be manual-sync** (consistent with the upgrade workflow driving syncs itself). Verify live.
- Every tier generates from **`main`** only. Nothing goes live until the MR is merged.

### 3.3 The exact layout a portal writes into
```
sites/
  configValues.yaml                         # global (don't touch)
  <site>/values.yaml                        # per site (optional)
  <site>/mces/<mce>/values.yaml             # per MCE: imagePath, dns, certificate, etcd, registries
  <site>/mces/<mce>/version.yaml            # per-MCE default mastertag (empty in export)
  <site>/mces/<mce>/hostedClusters/ocp4-<clusterName>.yaml   # ONE file per cluster  <-- portal writes this
```
- To create a cluster: **add one file** on a branch and open an MR to `main`. Nothing else should be added to the directory:
  - The appset globs `hostedClusters/*`, so any extra file becomes an Application.
  - CI globs `sites/*/mces/*/hostedClusters/*.yaml`.
- To delete a cluster, delete the file. The appset removes the Application. The connected chart's PostDelete hook then releases the segment; the air-gap chart has no such hook.
- New MCE: create the directory with a `values.yaml`. The hub Argo also needs a cluster secret named like the directory, and the MCE needs its own GitOps operator with repo credentials. These are manual steps.
- Cluster names are unique across the repo, and workflows find files by name under any `sites/*/mces/*/hostedClusters/` (`$ECO/workflows/shared/models/cluster_upgrade.py`).
- The day2 env convention comes from names like `ocp4-<env:prod|prep|test>-<name>-<site>`.

### 3.4 CI chain on the branch (platform-config `.gitlab-ci.yml`; `$SE/gitops/platform-config/README.md`, `scripts/SCRIPTS.md`)
On every push to a **non-main** branch (never on MR events, `[skip ci]` honoured):
- `allocate_segments`:
  - Steps: `get_changed_clusters` → `filter_frozen` → for each **new** file (no `vlanId` and no `dhcp_values`), `POST {WORKFLOWS_ORCHESTRATOR_URL}/workflows/segment-lifecycle/allocate-segment {"cluster":"<file stem>","values_branch":"<branch>"}`, then poll `GET /workflows/runs/{id}`.
  - The workflow, backed by Segments Manager, **pushes `vlanId` and `dhcp_values` onto that branch** with `[skip ci]`.
- `stage_mc_sources`: templates get `VLAN_ID`, `{CLUSTER_NAME}` and `{OPENSHIFT_VERSION}` substituted.
- `render_mc_configs` (butane), then `inject_configs` (writes `mcConfigMap` into the file).
- `commit_and_push` (`CI: Update mcConfigMap from mc-files [skip ci]`).
- `run_tests` and `validate_all_clusters` run in parallel, also on MRs.
- Result: **the MR branch receives commits from two bots** (the orchestrator and CI) after the author's push. It is mergeable only once that chain has finished.

---

## 4. End-to-end, from "I want a cluster" to "cluster ready"

### 4.1 Components
- **Hub** (central OpenShift): Argo CD tiers 1–2, the workflows orchestrator API and Temporal workers, segments-manager, server-scan, dhcp-scope-manager, Crossplane provider-http.
- **MCE** (per site, prep/prod): its own Argo CD (tier 3), HyperShift/MCE, the `inventory` namespace with InfraEnvs and Agents, herzi, Crossplane and cert-manager (air-gap).
- **Values repo** (platform-config / day1), **chart repo**, **argocd-platform repo**, **gitops-day2-prod** (sigs).
- Not in this slice: `$SE/../Architecture@2x.png` is a "Multi-site LLM platform" diagram (Envoy AI Gateway, llm-d, LMCache). It is unrelated to cluster provisioning; the only overlap is the hub naming `ocp4-prod-hub-site1`.

### 4.2 Order of events: what exists today
There is **no Day1/create-cluster workflow** in the workflows API (OpenAPI: segment-lifecycle, server-lifecycle, server-provisioning, cluster-upgrade, vm-lifecycle only).

| # | Step | Mechanism today | Manual / automated |
|---|---|---|---|
| 1 | Decide site, MCE, name, OCP version, nodepools (InfraEnv, replicas, MC configs) | human knowledge; copy a similar file | **MANUAL** |
| 2 | Write `ocp4-<name>.yaml` on a branch and push | git | **MANUAL** |
| 3 | Allocate VLAN segment, DHCP network | CI `allocate_segments` → orchestrator `allocate-segment` → Segments Manager → push to branch | automated (triggered by the push) |
| 4 | Render MachineConfigs into `mcConfigMap` | CI chain | automated |
| 5 | Review and merge the MR to `main` | GitLab MR | **MANUAL** |
| 6 | Application created for the file | tier-3 appset on the MCE (polls ~3 min) | automated |
| 7 | Sync the Application | **appears manual** (no `syncPolicy` in the exported configValues) | **MANUAL?** (verify) |
| 8 | Pre-create Secrets (pull, ssh, etcd key, LDAP, htpasswd) in `hcp-<cn>` | connected chart renders none; air-gap chart renders them from its own templates | **UNOWNED** (connected) / insecure (air-gap) |
| 9 | Namespaces, certs, DNS, DHCP scope, HostedCluster, ConfigMaps, NodePools | chart + Crossplane + cert-manager + HyperShift | automated after sync |
| 10 | Control plane up on the MCE | HyperShift | automated |
| 11 | Workers: NodePools claim free Agents labelled with the InfraEnv | HyperShift Agent CAPI | automated if Agents exist |
| 12 | Top up InfraEnv spares when demand rises | herzi → `add-server-to-mce` → server-scan / segment / provisioning → Agent | automated **only where the pool has `dryRunGrow: false`** (default true; not yet run on a real hub) |
| 13 | Register with day2 sig repos | connected chart Job (wave 100); air-gap: `APPLY-DAY2-COPY.md`, not ported | automated (connected) / **MANUAL** (air-gap) |
| 14 | "Ready" signal to the requester | nobody aggregates it: Argo app health, HostedCluster `Available`, NodePool ready replicas, herzi pool gauges | **UNOWNED** |
| 15 | Kubeconfig / console delivery | air-gap kubeconfig-sync CronJob and `cluster-go` shortcut | partly automated (air-gap) |
| Del | Delete file → Application deleted → resources gone → release segment | connected PostDelete hook (bridge); air-gap none | partial / **MANUAL** (air-gap segment release) |

### 4.3 Gaps (manual or unowned): what Wingman or the planned Day1 workflow fills
- **G1** Authoring the file. Today this means copy-paste plus tribal knowledge of InfraEnv names, `mc-files` names, conventions (`ocp4-<env>-<name>-<site>`, `allowDeletion: false`, zones need `name`) and the masters-first upgrade rule.
- **G2** Validation before push. Wingman can run the same checks:
  - InfraEnv exists on the MCE and is not herzi-ignored.
  - Config names resolve in `mc-files/`.
  - The name is unique repo-wide and follows the env convention.
  - The `helm template` dry-run of `validate_all_clusters.py` passes.
- **G3** Waiting for CI and segment allocation, and surfacing failures. Today a person watches the pipeline.
- **G4** MR approval and merge (human gate). Wingman already has an approvals model.
- **G5** Argo sync of the tier-3 Application, if it is manual, plus watching sync and health.
- **G6** Per-cluster Secrets in the connected chart. Nothing creates them, and Wingman should not put them in git.
- **G7** Capacity readiness:
  - Is herzi live (not dry-run) for the chosen InfraEnv?
  - Is the pool blocked, or in probe mode ("needs hardware")?
  - Who creates new InfraEnvs per MCE? That is unknown and not in these repos.
- **G8** Day2 registration in the air-gap.
- **G9** A single "cluster ready" status and notification to the requester.
- **G10** Deprovision. There is no workflow; segment release is a bridge hook (connected only).
- **G11** MCE onboarding: the directory and `values.yaml`, the hub Argo cluster secret, herzi install per MCE.
- **G12** The two chart copies and two `clusterName` conventions (prefix kept vs stripped) are not converged. A portal must know which environment it targets.

---

## 5. Wingman integration

### 5.1 What Wingman day1 does today (`$WM/apps/day1-service/src`)
- **Specs** (`specs/<name>.yaml` in a separate GitLab specs project) hold `day1.variables` and a **Jinja2 template of raw HyperShift manifests**.
  - `services/yaml_renderer.py` renders it into a multi-document YAML of `HostedCluster` and `NodePool` objects. Example: `$WM/scripts/seed-test-data.py`, where the HostedCluster is named `{{cluster_name}}` in namespace `{{mce_name}}` with a quay.io release image and `agentNamespace: {{mce}}-agents`.
- `services/cluster_service.py: create_cluster` commits that YAML to `DAY1_CLUSTERS_PATH_TEMPLATE = sites/{site}/mces/{mce}/hostedClusters` + `/{cluster}.yaml` (`config.py:42`). It uses branch `platform/{user}/create-cluster-{name}-{ts}`, MR title `[Wingman/Day1] Create cluster ...`, and prepends spec-name/version comments.
  - It calls the **sync** `gl.file_exists`, `gl.commit_files` and `gl.create_mr` inside async code, which goes against Wingman's own CLAUDE.md async rule.
- Dropdowns:
  - Sites and MCEs come from directory listing.
  - InfraEnvs come live from each MCE (`routers/mces.py` → `cluster_status_service.list_infraenvs`, namespace `MCE_INFRAENV_NAMESPACE`).
- Status (`cluster_status_service.py`): reads HostedCluster and NodePool conditions live. It assumes **HostedCluster name = full file stem (`ocp4-prod-web`)** in `hcp-<stem minus ocp4->`.
- `.wingman.yaml` sidecar per cluster (`path_resolver.day1_cluster_metadata`). The drift detector and webhook read it from the **same `hostedClusters/` directory**.

### 5.2 What it already gets right
- The repo layout `sites/<site>/mces/<mce>/hostedClusters/<file>.yaml` is exactly the current values-repo layout.
- One file per cluster, via MR, on a non-main branch. That branch push triggers the CI chain, as required.
- The InfraEnv dropdown is read from the MCE, which is the right source for `infraEnvName`.

### 5.3 What Wingman should produce instead
- A **values file for the hostedclusters-setup chart**, not manifests: `sites/<site>/mces/<mce>/hostedClusters/ocp4-<clusterName>.yaml` containing only the human-owned keys from §2.2 / §2.5:
  - `owner`, `mastertag`.
  - `nodepool[]` with `infraEnvName`, `replicas`, `labels.allowDeletion: false`, `configs`, and optional `name`, `nodeLabels`, `tuningConfig`.
  - Optional: `platform: kubevirt` plus KubeVirt fields, `imageContentSources`.
- Rework **specs** from "Jinja of manifests" to "a values preset / form schema". Examples: allowed `mastertag` versions (read from `upgrade/ladder.yaml` or MCE `version.yaml`), nodepool shapes (InfraEnv family plus default `configs` list per hardware), and labels. The output should be the YAML values above. Jinja can stay, rendering values instead of objects.
- Validate before opening the MR:
  - InfraEnv exists on that MCE (live), and the herzi pool is not ignored or dry-run (metrics or annotations).
  - Every `configs[].name` resolves under `mc-files/` (root, `virt/`, `kubevirt/`, `legacy/`, or the `templates/nm-conf-template-<hw>.bu` suffix rule).
  - The name is unique repo-wide and matches `ocp4-<env>-<name>-<site>`, with env equal to the MCE's env field.
  - Zones sharing an InfraEnv carry `name`.
  - Optionally run `helm template` with the 4 layered files plus the `clusterName` parameter, as `validate_all_clusters.py` does.
- After the MR is opened, **track the branch pipeline**:
  - The `allocate-segment` run (`GET /workflows/runs/{id}`; deterministic id).
  - The CI commits that append `vlanId`, `dhcp_values` and `mcConfigMap`.
  - Only then show "ready to merge".
- Post-merge status: read these from the MCE.
  - The tier-3 Argo Application `<file stem>` (sync, health).
  - `HostedCluster openshift-<clusterName>` in `hcp-<clusterName>`.
  - NodePools `<clusterName>-<infraEnvName>` (or explicit names).
  - herzi gauges for each InfraEnv (`herzi_pool_need`, `_blocked`, `_probe_mode`) to explain "waiting for hardware".
  - The orchestrator's `add-server-to-mce-<mce>_<infraEnv>_*` runs.
- Upgrades: write `mastertag` plus a top-level `workertag` in one commit (masters first), or better, delegate to the existing `cluster-upgrade` workflow API.

### 5.4 What Wingman should stop doing
- **Stop rendering HostedCluster/NodePool YAML.** The chart owns the objects. Raw manifests in the values repo would be fed to Helm as *values*, render nothing useful, and break CI (`inject_configs` and `validate_all_clusters` expect a values mapping).
- **Stop writing anything other than the one cluster file into `hostedClusters/`.** A `.wingman.yaml` sidecar there would match the tier-3 appset glob `hostedClusters/*` and become a bogus Application (clusterName `<x>.wingman`). It would also confuse the workflows' file lookup. Keep metadata in the MR description or commit trailer, or in a Wingman-owned path outside `sites/`.
- **Never write `vlanId`, `dhcp_values`, `mcFiles`, `mcConfigMap`, `clusterName` or `platform: agent`.** These are automation-owned or defaults.
- Stop hardcoding the release image, `pullSecret` or `agentNamespace`. They come from MCE/global values (`imagePath`, `hostInventory`).
- **Fix the status lookup naming:**
  - HostedCluster = `openshift-<clusterName>` in `hcp-<clusterName>`.
  - `clusterName` = the file's `clusterName` key if present, else stem minus `ocp4-` (air-gap convention). On the connected copy it is the full stem; make it configurable.
- **Do not force-push or rewrite the MR branch.** CI and the orchestrator commit onto it. Re-read the branch head before modifying an open MR.
- Do not treat the MR merge as "cluster created". Readiness is gated on Argo sync, HyperShift and Agent capacity (herzi).

### 5.5 What the planned Day1 workflow would likely take over (Wingman then calls it)
- Allocating the segment up front instead of from CI.
- Pushing the file and opening the MR, then waiting for CI.
- After merge: triggering the Argo sync and creating the per-cluster Secrets.
- Watching the HostedCluster and NodePools, and confirming herzi capacity.
- Registering with day2 and notifying the requester.
- A matching deprovision (release segment, which replaces the PostDelete hook).
- Wingman would then become the form, validation, approval and status UI over `POST /workflows/<day1>/...` and `GET /workflows/runs/{id}`, mirroring how upgrades already work through `cluster-upgrade`.
