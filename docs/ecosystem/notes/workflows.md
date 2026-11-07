# workflows (Temporal "Cluster Orchestrator"), notes for the Wingman modernization

Sources:
- Repo `github.com/team-redbull/workflows`, read-only clone at
  `/private/tmp/claude-501/-Users-roiblum-Downloads-scripts-wingman/60427645-e4b9-4b8e-94ad-b88eed448a81/scratchpad/eco/workflows`.
  It is a **shallow clone of `main` only**: 50 commits, 2026-10-31 to 2026-11-05, head `00b3324`. Remote branches are not visible.
- Live API: `<sandbox URL, see CLAUDE.local.md>`. OpenAPI saved to
  `/private/tmp/claude-501/-Users-roiblum-Downloads-scripts-wingman/60427645-e4b9-4b8e-94ad-b88eed448a81/scratchpad/notes/workflows-orchestrator-openapi.json`
  ("Cluster Orchestrator API" 0.1.0, OpenAPI 3.1, **25 operations / 38 schemas, no securitySchemes**).
- Live docs: `<sandbox URL, see CLAUDE.local.md>`. Deployed tag `v1.0.71`, byte-identical to the repo's `docs/site` apart from the version stamp.
- Only GETs were made against live systems. Nothing was started, signalled or cancelled.

Key rationale files: `README.md` (61 KB), `CLAUDE.md` (108 KB; §2 naming/API, §4 every external dependency, §5 Temporal rules, §9 deploy/auth), `.claude/rules/*.md`, `docs/site/**` (one page per workflow), `docs/design/*.md`.

---

## 0. Architecture in one paragraph

- **Brain**: one deployment, `workflows-orchestrator` (`workflow_domains/main_worker_init.py`), runs every workflow, **one Temporal Worker per workflow queue**.
- **API**: `workflows-orchestrator-api` (`workflow_domains/api.py`), FastAPI on the same image. In-cluster it is ClusterIP `:8080` plus an OpenShift Route, namespace `redbull-workflows`.
- **Limbs**: one activity-worker deployment per credential set, `activities/<domain>/worker_init.py`, chart `<domain>-worker`.
  - Limbs that write to an MCE run **inside that MCE** and poll a per-MCE queue `<domain>-activity-<mce>`. Workers dial out to Temporal, so no cross-cluster kubeconfig exists anywhere (`shared/consts.py`).
- **Contract layer**: `shared/` (pydantic models plus `@activity.defn` interfaces).
- **Deployment**: prod charts are vendored in `team-redbull/redbull-platform/gitops/charts/<service>/`. One ApplicationSet sweeps `gitops/services/<service>/app.yaml`.
- **Images**: built to ghcr through the reusable workflow in `team-redbull/.github`, tagged `vX.Y.Z`; CI bumps the tag cross-repo into redbull-platform (`.github/workflows/build.yml`).
- **Stack**: Python, `temporalio`, pydantic v2, FastAPI, git through a subprocess, httpx.

---

## 1. Workflow catalog

### 1a. IMPLEMENTED: registered in `_WORKER_SPECS` (`workflow_domains/main_worker_init.py:86-106`) and routed in the live OpenAPI

| # | Workflow (type) | Domain | Workflow queue / activity queue | Workflow id | Route |
|---|---|---|---|---|---|
| 1 | initialize-segment (`InitializeSegmentWorkflow`) | segment-lifecycle | `initialize-segment-workflow` / `segment-lifecycle-activity` | `initialize-segment-<network>` | `POST /workflows/segment-lifecycle/initialize-segment` (+`/bulk`) |
| 2 | allocate-segment (`AllocateSegmentWorkflow`) | segment-lifecycle | `allocate-segment-workflow` / same | `allocate-segment-<TYPE>-<cluster>` | `POST …/allocate-segment` |
| 3 | release-segment (`ReleaseSegmentWorkflow`) | segment-lifecycle | `release-segment-workflow` / same | `release-segment-<TYPE>-<cluster>` | `POST …/release-segment` |
| 4 | add-server-to-mce (`AddServerToMceWorkflow`) | server-lifecycle | `add-server-to-mce-workflow` / `server-lifecycle-activity-<mce>` (+1 call on segment queue) | slot `add-server-to-mce-<mce>_<infraEnv>_<1..100>`, or named `add-server-to-mce-<mce>_<server>` | `POST /workflows/server-lifecycle/add-server-to-mce` |
| 5 | remove-server-from-mce (`RemoveServerFromMceWorkflow`) | server-lifecycle | `remove-server-from-mce-workflow` / per-MCE | `remove-server-from-mce-<server>` | `POST …/remove-server-from-mce` |
| 6 | uninstall-server-from-hc (`UninstallServerFromHcWorkflow`) | server-lifecycle | `uninstall-server-from-hc-workflow` / per-MCE | `uninstall-server-from-hc-<server>` | `POST …/uninstall-server-from-hc` |
| 7 | publish-infraenv-to-pxe-server (`PublishInfraEnvToPxeServerWorkflow`) | server-lifecycle | `publish-infraenv-to-pxe-server-workflow` / per-MCE | `publish-infraenv-to-pxe-server-<mce>-<infraEnv>` | `POST …/publish-infraenv-to-pxe-server` |
| 8 | provision-dell-server (`ProvisionDellServerWorkflow`) | server-provisioning | `provision-dell-server-workflow` / `server-provisioning-activity` | `provision-dell-server-<idrac ip>` | `POST /workflows/server-provisioning/provision-dell-server` (+`/bulk`) |
| 9 | create-vm (`CreateVmWorkflow`) | vm-lifecycle | `create-vm-workflow` / `vm-lifecycle-activity` | slot `create-vm-<mce>_<infraEnv>_<slot>` | `POST /workflows/vm-lifecycle/create-vm` |
| 10 | upgrade-cluster (`UpgradeClusterWorkflow`) | cluster-upgrade | `upgrade-cluster-workflow` / `upgrade-gitops-activity` (hub), `cluster-upgrade-activity-<mce>`, `upgrade-agent-activity-<mce>` | `upgrade-cluster-<cluster>` | `POST /workflows/cluster-upgrade/upgrade-cluster` + 10 decision routes |
| 11 | upgrade-control-plane (`UpgradeControlPlaneWorkflow`) | cluster-upgrade | `upgrade-control-plane-workflow` | `upgrade-control-plane-<mce>_<slot>` | none (child of 10, driven by signals) |
| 12 | upgrade-targets (`UpgradeTargetsWorkflow`) | cluster-upgrade | `upgrade-targets-workflow` / hub limb | `upgrade-targets-<cluster>` (USE_EXISTING) | `GET /workflows/cluster-upgrade/upgrade-targets?cluster=` (**synchronous**, 60 s) |
| — | legacy `InstallServerWorkflow`, `RemoveServerWorkflow`, `UninstallServerWorkflow`, `PublishInfraEnvBootWorkflow` | server-lifecycle | `install-server-workflow`, … | old ids | old routes answer **410** with the new name. Kept only so pre-2026-11-01 runs replay; to be deleted. |

**Deployment reality of the limbs** (README:100-113, CLAUDE.md §1/§9). Implemented in code does not mean deployed in prod:

| Limb | Status |
|---|---|
| segment-lifecycle-worker | Has a `gitops/services/` entry, so it is deployed. |
| server-lifecycle-worker | Per MCE, via an ApplicationSet keyed on cluster-Secret labels `workflows.redbull/server-lifecycle` and `workflows.redbull/mce-cluster` (`deploy/argocd/server-lifecycle-worker-applicationset.yaml`). |
| server-provisioning-worker | **No services entry: nothing deploys it.** |
| vm-lifecycle-worker | Chart written 2026-11-05, **not on redbull-platform main yet**. Also needs the kv-capacity / kv-vm-api agents on each KubeVirt cluster; until then runs wait with every cluster `no-agent`. |
| cluster-upgrade limbs (3) | **No services entry; installed by hand on the sandbox.** Docs page: "Built, and run on a sandbox HostedCluster — not in production yet" (`docs/site/cluster-upgrade/upgrade-cluster.html`). |

**Live sandbox Temporal, as seen by GET `/workflows/runs?workflow_type=…` on 2026-11-07** (saved under `/private/tmp/claude-501/-Users-roiblum-Downloads-scripts-wingman/60427645-e4b9-4b8e-94ad-b88eed448a81/scratchpad/live-runs/`):
- Runs exist only for cluster-upgrade:
  - `UpgradeClusterWorkflow`: 8 runs, all id `upgrade-cluster-ocp4-upgrade-demo` (3 COMPLETED, 5 CONTINUED_AS_NEW), 2026-10-31 to 11-01.
  - `UpgradeControlPlaneWorkflow`: 3 runs.
  - `UpgradeTargetsWorkflow`: 2 runs (1 TIMED_OUT).
- Every other type has 0 runs, so this sandbox has exercised only cluster-upgrade.
- Caveat: the list endpoint returns `[]` for *any* type name, including a nonexistent one such as `CreateClusterWorkflow`. Existence of a workflow is proven by the OpenAPI routes and `_WORKER_SPECS`, not by the run lists.

#### Detail per implemented workflow (inputs → touches → outputs → humans)

**Group A: network segments (segment-lifecycle; hub limb; credentials: Segments Manager token, day1 git push token, DHCP API token)**

1. **initialize-segment**: create a segment, born Available with no type.
   - Input `InitializeSegmentRequest {segment (CIDR), site, vlan_id 1..4094, epg_name, dhcp=true}`; extra fields forbidden, so `type` gets a 422.
   - Bulk route takes `{segments:[…]}`, starts one run per segment, and returns a per-item report.
   - Touches the Segments Manager: `POST /api/segments`. The Segments Manager is the validator of record, so a bad definition shows up as a FAILED run, not a 4xx.
   - Result `{segment}`. Phases `pending → creating-segment → completed`. No human step.
2. **allocate-segment**: reserve an HC segment for a hosted cluster and record it in the day1 file.
   - Input `AllocateSegmentRequest {cluster, values_branch (REQUIRED, the branch the cluster file lives on), type=HC}`. Only HC is supported.
   - Steps:
     - Clone the day1 repo at that branch; find exactly one `sites/<site>/**/<cluster>.yaml`. The site comes from the path, cross-checked against SM `GET /api/sites`.
     - SM allocate, then read it back (status, cluster, vlan and type must all match).
     - Append a marker block (`# === Added By Segment-Allocation Workflow ===`, `vlanId:`, `dhcp_values: {network, exclusions}`) and push to **that branch** with `[skip ci]`.
   - Result `{cluster, site, type, vlan_id, segment, epg_name, values_branch, commit_sha, values_updated}`. Phases `resolving-site → allocating-segment → verifying-allocation → updating-values-repo → completed`.
   - **Today's caller is the day1 repo's CI pipeline** (see §3). It ends at the push; the DHCP scope appears only after a human merges.
   - Files: `workflow_domains/segment_lifecycle/allocate_segment.py`, `activities/segment_lifecycle/values_repo.py`.
3. **release-segment**: give a decommissioned cluster's segment back.
   - Input `{cluster, type=HC}`.
   - Steps: SM lookup (none found is a completed no-op, `released:false`); DHCP API `GET` scope, `DELETE` it if it survived, read back; re-read the owner, release, read back Available.
   - **Today's caller is the Argo CD PostDelete hook** in `helm-charts-hostedclusters-setup` (`templates/release-segment-hook.yaml`), which retries POSTs for up to 55 min.
   - Phases `locating-allocation → removing-dhcp-scope → releasing-segment → verifying-release → completed`.

**Group B: server onboarding into an MCE (server-lifecycle; one limb per MCE; credentials: server-scan ADMIN token, BMC creds per vendor, PXE-map token, MCE ServiceAccount RBAC)**

4. **add-server-to-mce**: fill an InfraEnv with ONE server per run.
   - Input `AddServerToMceRequest {infra_env, mce_cluster (with or without ocp4-), namespace=inventory, server_names? (str|list≤20), count? 1..20, candidate_count? 1..20, labels{}}`. There is deliberately no `vlan_id`.
   - Request shapes:
     - Pool draw: query `^ocp-<infra_env>`.
     - `count`: N parallel runs on free slots.
     - Named: one run per name.
   - Touches:
     - Segments Manager: the MCE's INVENTORY segment found by cluster name gives the VLAN.
     - server-scan: `GET /servers/available`; `POST`/`DELETE /servers/{id}/reservation` lock, 2 h, then 24 h after success.
     - MCE: Secret, BareMetalHost, NMStateConfig; InfraEnv pre-check; waits up to 1 h for an **Agent** (matched by bond MAC).
     - PXE VM `pxe-map-api`: for IPMI/Cisco blades only.
   - Loops over candidates with rollback.
   - Result: server_id/name, vlan_id, bmc vendor/address, bond_macs, boot_mac, agent_name, attempts, reservation_expires_at, and more.
   - Progress `{phase, server_name, activity_queue}`. `activity_queue` tells you which MCE has no worker when a run is stuck.
   - Callers: humans via `/ui/server-lifecycle`, and **herzi** (the controller that keeps InfraEnvs filled; `herzi/README.md:14,135`).
   - No human approval step.
5. **remove-server-from-mce**: take an unbound server out of the inventory.
   - Input `{server_name, mce_cluster, namespace=inventory}`.
   - Refuses if the Agent is bound (`AgentBoundToClusterError`).
   - Steps: power off; delete BMH and NMStateConfig, then the Agent last; clear PXE-map MACs on the MCE's own site; verify nothing is left; release this MCE's server-scan lock.
   - Phases `inspecting → powering-off → removing-host → removing-agent → removing-pxe-boot → verifying → releasing-server`.
6. **uninstall-server-from-hc**: take a server out of its hosted cluster, then out of the MCE.
   - Input `{server_names (str|list≤20), mce_cluster, namespace=inventory}` only. There is no HC or NodePool field: server-scan and the Agent binding say where the server is.
   - Steps:
     - Check server-scan membership; inspect BMH, Agent, AgentMachine, Machine and HostedCluster; take the lock.
     - Delete the CAPI Machine; wait through `draining` (20 min) and `unbinding` (1 h).
     - Verify the AgentMachine, the Node (through the HostedCluster admin kubeconfig) and the Agent.
     - Run **remove-server-from-mce as an awaited child**, then release the lock.
   - NodePool replicas are never changed, so the NodePool backfills (a replacement, not a shrink). Who owns a shrink is undecided (CLAUDE.md:493-495).
   - Also cleans up what broken HyperShift deletions leave behind.
7. **publish-infraenv-to-pxe-server**: write an InfraEnv's iPXE boot entry to the site's PXE VM (`/var/www/pxe-map/<mce>/<infraEnv>.ipxe`).
   - Input `{mce_cluster, infra_env, namespace=inventory}`.
   - Phases `resolving-site → validating-infraenv → publishing`. Waits up to 10 min for `ImageCreated`.

**Group C: bare-metal provisioning (server-provisioning; hub limb; NOT deployed)**

8. **provision-dell-server**: take a Dell that only has an iDRAC IP to "configured, ready for add-server-to-mce".
   - Input `{idrac_ip, region?}`. The region is derived from the IP prefix (`workflow_domains/server_provisioning/regions.py`), so an unknown prefix is a 422. Bulk route `{servers:[…]}`.
   - Touches iDRAC (Redfish, root password probe), Dell OME (discover, deploy template per (model, firmware) from `DELL_TEMPLATES`), BOSS RAID1 + PERC non-RAID, the naming service (`SERVER_NAMER_URL`), and a server-scan safety check.
   - Final name `ocp-dell-<model>-<region>-<N>c-<N>gb-<N>tb-<tag>`.
   - Phases `probing-idrac → reading-identity → checking-server-scan → discovering-in-ome → deploying-template → verifying-root-password → [rediscovering-in-ome] → configuring/applying/verifying-storage → naming-server → verifying-name → completed`.
   - Cisco, HPE and Intersight provisioning are planned (README:20).

**Group D: KubeVirt workers (vm-lifecycle; hub limb, no k8s credentials; not yet deployed)**

9. **create-vm**: make one Halted VirtualMachine with a fixed MAC on the best-fitting KubeVirt cluster of the InfraEnv's zone. This is the step before add-server-to-mce for KubeVirt InfraEnvs.
   - Input `{mce_cluster (must parse as ocp4-<env>-mce-<site>-<letter>), infra_env (<conf>[-<letter>]-zone-<zone>-<cpu>, not -metal), namespace=inventory, count?≤20}`.
   - Touches the day1 repo (lists `sites/<site>/mces/ocp4-seed-<site>-<zone>/hostedClusters/` at main), `kv-capacity` and `kv-vm-api` agents per KV cluster (bearer tokens; TLS **not verified by default**), and best-fit placement under `HEADROOM_BUFFER_PERCENT`.
   - Phases `listing-kv-clusters → ranking-kv-clusters → creating-vm → awaiting-root-disk → [removing-vm] → completed`.
   - The add-server-to-mce KubeVirt branch (start create-vm as a child) is a planned "later step" (CLAUDE.md:674).

**Group E: hosted-cluster upgrade (cluster-upgrade; three limbs; sandbox only)**

10. **upgrade-cluster**: upgrade one HyperShift HostedCluster **only through day1 git commits plus an Argo CD sync**. It never patches the HostedCluster or NodePool.
    - Input `UpgradeClusterRequest {cluster (day1 file name, regex ^[a-z0-9]…), target_version | target_minor, nodepool_mode manual|auto, nodepool_order?, max_unavailable{np: int|"33%"}?, workers_to_target=true, auto_approve=false (wave 0/1 only), requested_by}`.
    - Touches:
      - day1 repo: edits `mastertag`, `nodepool[].workertag`, `inPlace.maxUnavailable`, `pausedUntil`; runs day1's own validator `DAY1_VALIDATE_COMMAND`.
      - Argo CD: syncs the multi-source Application on the MCE at the day1 commit.
      - Mirror registry v2 plus `oc adm release info`.
      - day2 repo (read), Brain repo (writes incident pages).
      - LLM **upgrade agent service** (`team-redbull/k8s-agent`, an agent-sandbox `Sandbox` per MCE).
      - Admin-ack inside the hosted cluster.
    - **Human in the loop (Temporal Updates)**: approve, approve-admin-ack, continue (per NodePool), confirm-day2, pause, resume, abort, retry, and approve/reject an agent action. Every body needs `by` (and abort/admin-ack need `reason`).
    - Phases: `UpgradePhase` in `shared/models/cluster_upgrade.py:222`.
    - Progress includes the plan, `waiting_for`, `pending_actions`, `last_verdict` and a human-readable `log`.
    - Result `{outcome done|cancelled|aborted, mce_cluster, cluster, plan, steps_completed, control_plane_version, nodepool_versions, log}` (verified against a live run).
    - Design doc: `docs/upgrade/DESIGN.md` in a *separate* "Cluster-AutoUpgrade workspace", not in this repo.
11. **upgrade-control-plane**: the child for one control-plane step, on a per-MCE slot (the slot is the concurrency cap). The parent drives it with signals.
12. **upgrade-targets**: a synchronous read for the "New upgrade" form.
    - Returns `UpgradeTargets {cluster, mce_cluster, mce_version, control_plane_version, supported_minors, ladder_revision, targets[{version, minor, steps, control_plane_steps, newest_in_minor, must}], nodepools[Day1NodePool], nodepool_order}`.
    - Errors: 404 no such cluster, 409 unusable file, 504 no limb.

There are **no day2/addon workflows** in this repo. cluster-upgrade only reads day2 layers and has `confirm-day2`.

### 1b. PLANNED / NOT BUILT (no code, no queue constant, no route, no stub; no branch visible in the shallow clone)

| Planned item | Where it is mentioned | What is said |
|---|---|---|
| **create-cluster (Day1)** | `CLAUDE.md:818-830, 842, 1173`; `shared/models/segment_lifecycle.py:287, 365`; `docs/site/segment-lifecycle/allocate-segment.html` | "Until a create-cluster workflow exists, allocate-segment is a step inside the day1 values repo's GitLab pipeline". A future create-cluster "keeps this shape: it merges AFTER its allocate-segment child returns". It will verify the DHCP scope after its merge, with a bounded deadline, comparing the EXCLUSIONS it pushed, and reuse `get_dhcp_scope` / `DhcpScopeState` / `DhcpApiError`. |
| **deprovision-cluster** | `CLAUDE.md:859-872`; `README.md:762-764`; `workflow_domains/segment_lifecycle/release_segment.py:19`; `docs/design/release-segment.md:29`; `helm-charts-hostedclusters-setup/README.md:114` | It owns the teardown: delete the file, a bounded wait for the Application to disappear, start release-segment as a child. The PostDelete hook is then deleted. |
| create-hosted-cluster / delete-hosted-cluster procedures (spec) | `eco/kubevirt-workflows/docs/procedures/03-create-hosted-cluster.md`, `05-delete-hosted-cluster.md` (another agent owns that repo) | See §3b. Design only. |
| add-server-to-mce, KubeVirt branch | `CLAUDE.md:674-675` | Start create-vm as an awaited child when the InfraEnv is KubeVirt; "NO branch exists yet". |
| Cisco / HPE / Intersight provisioning | `README.md:20` | "get their own workflows later". |
| cluster-upgrade remaining work | `docs/site/cluster-upgrade/upgrade-cluster.html` "Not yet" | The agent's judge and tier-1 tools, RBAC/admission fences, Argo apps for the 3 workers, fleet waves plus circuit breaker. |
| NodePool shrink ownership | `CLAUDE.md:493-495` | "NOT DECIDED", taken to the team. |
| **ClickCluster Platform UI** | `workflow_domains/*/ui.py`, `CLAUDE.md:191-199`, docs pages | `/ui/server-lifecycle` and `/ui/cluster-upgrade` are "temporary … until the ClickCluster Platform UI exists". **This is the slot Wingman would fill.** ("ClickCluster" is also the platform name in segments-manager VLAN groups.) |
| UPI | — | No UPI workflow anywhere. In kubevirt-workflows' architecture, UPI is the *manual* install of Seed clusters and the Customer MCE (`architecture.md` AD17, `12-create-customer-mce.md`). |

---

## 2. Orchestrator API (what Wingman would call)

Base: `workflow_domains/api.py`. Routers: `workflow_domains/<domain>/router.py`, `workflow_domains/routers/{runs,models,slots,deps}.py`.

### Starting a workflow
- `POST /workflows/<domain>/<workflow>` with a JSON body. It is always **async**.
  - One run: `202 {workflow_id, run_id}` (`StartWorkflowResponse`).
  - Multi-run (bulk, `count`, a `server_names` list): `202 {started, already_running, failed, results[ {workflow_id, status started|already_running|failed, run_id?, error?, slot?|server_name?|segment?|idrac_ip?} ]}`.
  - In the OpenAPI, add-server-to-mce, uninstall-server-from-hc and create-vm declare their 202 without a schema, because they return one shape or the other.
- Status codes:

  | Code | Meaning |
  |---|---|
  | 202 | Started (or multi-run report). |
  | 409 | Same deterministic id already running. Pool and slot routes don't 409 unless all 100 slots are busy. |
  | 410 | Renamed route. |
  | 422 | Pydantic validation (`extra="forbid"` on every request model). |
  | 502 | Temporal refused the start. |

  Per-router counts: `segment_lifecycle/router.py` 202/409; `server_lifecycle/router.py` 202/409/410/502; `server_provisioning/router.py` 202/409/422; `vm_lifecycle/router.py` 202/409/502.
- Pool routes are **not retry-safe**: a double-click installs two servers or creates two VMs (README:484-487).

### Status, progress and result of one run
- `GET /workflows/runs/{workflow_id}` returns `WorkflowRunStatusResponse {workflow_id, workflow_type, status, progress?, result?, error?}` (`workflow_domains/routers/runs.py:85-162`).
  - `status` is the Temporal status name: RUNNING / COMPLETED / FAILED / CANCELED / TERMINATED / TIMED_OUT / CONTINUED_AS_NEW.
  - `progress` comes from the workflow's `@workflow.query progress` (5 s timeout, best effort). It is returned while RUNNING **and** after failure. Every workflow defines one.
  - `result` is set when COMPLETED. `error` is the root-cause message on failure; it carries the error type name, e.g. `AgentNeverAppearedError`.
  - 404 for an unknown id.
  - `progress` and `result` are **untyped JSON** in the OpenAPI. Their real shapes are the pydantic `*Progress` / `*Result` models in `shared/models/<domain>.py`; e.g. `AddServerToMceProgress` is at `server_lifecycle.py:773`, `UpgradeClusterProgress` at `cluster_upgrade.py:364`.
- `GET /workflows/runs?workflow_type=<WorkflowClassName>&limit=1..200` returns `[{workflow_id, workflow_type, status, start_time, close_time}]`, newest first.
  - Filtering is by type only: no cluster, MCE or user filter and no pagination cursor.
  - It needs the Temporal **class name**, e.g. `UpgradeClusterWorkflow`, not the route name.
  - Per-cluster views have to filter client-side on the id prefix: `upgrade-cluster-<cluster>`, `allocate-segment-HC-<cluster>`, `add-server-to-mce-<mce>_`, `create-vm-<mce>_`.

### What does NOT exist
- No endpoint lists workflow types. Use the OpenAPI as the catalog: tags are domains, paths are workflows. The docs site's `docs/site/assets/nav.js` `CATALOGUE` is the human catalogue.
- No generic **cancel / terminate** endpoint. The one exception is upgrade-cluster's `abort`, a Temporal Update. Other runs are cancelled from the Temporal UI or CLI; README:224 says "operator cancels".
- No event-history endpoint. Use the Temporal UI; upgrade-cluster's `progress.log` / `result.log` is the human log.
- No streaming (no SSE or websockets). Clients **poll**: both temporary UIs poll every 10 s (`POLL_MS = 10000` in `workflow_domains/*/ui/index.html`).
- No dry-run. For upgrade-cluster, starting the run is the dry run: it plans, runs preflight, and waits for `approve` with nothing committed.

### Human decisions (upgrade-cluster only today)
- `POST /workflows/cluster-upgrade/upgrade-cluster/{workflow_id}/{approve|approve-admin-ack|continue|confirm-day2|pause|resume|abort|retry}`.
- `POST …/{workflow_id}/actions/{action_id}/{approve|reject}`.
- Bodies:
  - `DecisionRequest {by, reason?}`
  - `AdminAckApprovalRequest {by, reason}`
  - `AbortRequest {by, reason}`
  - `ContinueRequest {by, nodepool?}`
  - `ActionDecisionRequest {by}`
- Answers: `200 {workflow_id, decision}`; **409** refused by the run's validator (with the reason); 404 no such running run; 504 no brain worker; 500 otherwise.
- The workflow side is Temporal **Updates with validators**, never signals (CLAUDE.md:1012-1025).

### Auth model: **NONE**
- `api.py` has no auth, the OpenAPI has no securitySchemes, and nothing checks roles. The live API answered every GET anonymously.
- CLAUDE.md:1305-1308: "`workflow_domains/api.py` has NO auth of its own; anyone who can reach that hostname can start a workflow — release-segment's route ends in a DHCP scope DELETE…". The suggested mitigation there is disabling the Route.
- The temporary UIs "add no auth: the API has none".
- **No CORS middleware.** The only cookie is the OpenShift router's sticky cookie. A browser on Wingman's origin cannot call the API directly; Wingman must proxy server-side.
- Identity is a free-text `by` / `requested_by` field recorded in the run log, trusted as sent.
- Outbound credentials live in limb Secrets: SM token, day1 git token, DHCP token, server-scan admin token, BMC/OME/iDRAC creds, KV agent tokens.
  - None are committed in this repo (`.env.example` has placeholders; chart values use `existingSecret`).
  - CLAUDE.md §8 says redbull-platform's segment-lifecycle chart renders `dhcp-api-token` from a **committed** value `secrets.dhcpApiToken` (a copy of `gitops/charts/dhcp-scope-manager/charts/dhcp-api-token/values.yaml`). That is a secret in git in redbull-platform, not read here.
- Internal address for a server-side proxy: `workflows-orchestrator-api.redbull-workflows.svc:8080`.

---

## 3. "Create a new hosted cluster": as it works TODAY (no Day1 workflow) and as planned

### 3a. Today: a git and CI process with two workflows bolted on

Prerequisites (each is its own workflow, run by people or controllers, not chained):
1. Segments exist at the site: **initialize-segment** (or the Segments Manager UI). The MCE has an INVENTORY segment allocated.
2. Physical servers are provisioned and visible in server-scan: **provision-dell-server** (Dell only, not deployed yet), or by hand. server-scan collects every 6 h.
3. The InfraEnv exists on the MCE. No workflow creates InfraEnvs; that gap is noted in kubevirt-workflows `GAPS.md:51`. IPMI sites need **publish-infraenv-to-pxe-server**.
4. The InfraEnv is filled with Agents: **add-server-to-mce** (bare metal), called by **herzi** or by people. For KubeVirt: **create-vm**, then add-server-to-mce (the chaining is not built).

The cluster itself:

5. A human writes `sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml` in the **day1 repo** on a non-main branch and opens an MR/PR. **This is exactly what Wingman's day1 service does today.**
   - Repo: `gitops-day1-platform-config`. `.env.example:24` points at `https://github.com/team-redbull/gitops-day1-platform-config.git`, but the docs speak of a "GitLab pipeline" and `$CI_COMMIT_BRANCH`. Possibly prod/air-gapped is GitLab and the sandbox is GitHub; **verify**.
6. The day1 repo CI pipeline (non-main branches only):
   - For each changed cluster file, `POST /workflows/segment-lifecycle/allocate-segment {"cluster","values_branch":"$CI_COMMIT_BRANCH"}`. A 409 means it is already running: poll the same id.
   - Poll `GET /workflows/runs/allocate-segment-HC-<cluster>` until COMPLETED.
   - `git pull --ff-only` to get the workflow's `[skip ci]` commit with `vlanId` + `dhcp_values`; run `generate_mc_files` (MachineConfig files from vlanId); push back (needs `--autostash`).
   - Source: `docs/site/segment-lifecycle/allocate-segment.html`, "Where it runs".
7. **A human merges to main.** Argo CD reads main only.
8. On the MCE, Argo CD's `hcAppset` renders `helm-charts-hostedclusters-setup` as a multi-source Application (chart + day1 as `ref: values`), merging value layers `sites/configValues.yaml → sites/<site>/values.yaml → sites/<site>/mces/<mce>/values.yaml → cluster file`. It produces:
   - HostedCluster `openshift-<clusterName>` in `hcp-<clusterName>`;
   - NodePools (`.name`, else `<clusterName>-<infraEnv>`);
   - the Crossplane DHCP-scope `Request` (provider-http creates the scope);
   - a day2 registration Job;
   - the release-segment PostDelete hook.
   Sources: `activities/day1_repo.py` docstring; `helm-charts-hostedclusters-setup/Chart.yaml:6`.
9. NodePools bind free Agents. No workflow waits for the control plane or the workers.
10. Day2 goes through gitops-day2-prod (another agent).
11. Later: **upgrade-cluster** for upgrades; **uninstall-server-from-hc** to pull specific servers.
12. Decommission: delete the file on main. Argo deletes the Application; the PostDelete hook POSTs **release-segment**.

What the user supplies in that path today: only the cluster file. The file carries the keys the workflows read: `clusterName?`, `platform` (agent|kubevirt; kubevirt means the cluster's nodes are VMs), `mastertag` (release, e.g. `4.18.56-x86_64`), `nodepool[] {name, workertag, infraEnvName, replicas, nodeLabels{topology.kubernetes.io/zone}, upgradeType, inPlace.maxUnavailable, agentLabelSelector}`, `upgrade {wave, nodePoolOrder}`, `pausedUntil`. `vlanId` and `dhcp_values` are added by allocate-segment.

**UPI**: no workflow. UPI is manual (Seed clusters, Customer MCE) per kubevirt-workflows.

### 3b. Planned Day1 workflow (design material only, not implemented)

From workflows (`CLAUDE.md:818-843`, `shared/models/segment_lifecycle.py:287, 365`):
- The workflow becomes the entry point: callers POST, the run does everything. "Anything a workflow's outcome depends on belongs INSIDE the run" (CLAUDE.md:773-779).
- It runs **allocate-segment as a child** (same `values_branch` shape), then the merge, then a **bounded DHCP-scope verification** after the merge (compare exclusions; reuse `get_dhcp_scope`, `DhcpScopeState`).

From `kubevirt-workflows/docs/procedures/03-create-hosted-cluster.md` (spec, 2026-10-21/22):

| Aspect | Spec |
|---|---|
| Id | `create-hosted-cluster-<cluster>` |
| Trigger | "Customer, via the self-service catalog or a ticket" (i.e. a portal like Wingman) |
| Inputs | `cluster`, `hub` (MCE), `release_image` (pinned by **digest**), `worker_types[]` (per-zone replica counts, ≥3 so every zone gets one), `values_branch`, `pull_secret_ref`, `ssh_key_ref` |
| Preconditions | Hub healthy and its version supports the release; an InfraEnv for every worker type in all 3 zones; a free segment at the site |
| Writes | Git only |
| Ends at | Control plane available. It does not wait for workers. |

Phases:
1. `validating`: name free, hub known, pools exist.
2. `allocating-segment` (HC).
3. `verifying-allocation`.
4. `composing`: HostedCluster plus a NodePool per zone per worker type.
5. `committing`: one commit on `values_branch`.
6. **Human merge to main.**
7. `awaiting-control-plane`: bounded, on the hub queue.
8. `completed`: reports the kubeconfig secret name and the NodePools.

Open questions in the spec:
1. Who picks the hub. Hubs are one per OCP version band per site.
2. Whether the merge stays manual.
3. Whether mixed worker types are allowed.

Missing: **admission/capacity pre-flight**.

Mismatch to resolve: the spec says "compose manifests", but production renders day1 **values files** through the hostedclusters-setup chart. Composing a values file is what Wingman's Jinja template does.

`05-delete-hosted-cluster.md` phases:
1. `validating` (`confirm` required)
2. `draining`
3. `removing-manifests`
4. human merge
5. `awaiting-prune`
6. `awaiting-release` (Agents unbound)
7. `scrubbing` (disk wipe; unverified, manual for now)
8. `deleting-scope`
9. `releasing-segment`
10. `verifying`

It replaces the PostDelete hook. Workflows CLAUDE.md agrees on deprovision-cluster.

Likely reuse by a Day1 workflow:
- allocate-segment (child) plus `values_repo.py` (branch append).
- `activities/git_repo.py` and `activities/day1_repo.py` (clone, layer-merged read, `list_cluster_files`).
- upgrade-gitops' compare-and-set day1 edits and `DAY1_VALIDATE_COMMAND`.
- cluster-upgrade-worker's per-MCE HostedCluster reads and Argo Application sync/watch (for `awaiting-control-plane`).
- upgrade-targets and the release ladder, for offering valid releases.
- `shared/cluster_names.py`, `shared/infraenv_names.py` (naming parsers).
- Capacity stays separate (herzi + add-server-to-mce / create-vm), per the "creates demand, does not satisfy it" principle.

---

## 4. Conventions

- **Paths**: `/workflows/<domain>/<workflow>` to start; `/workflows/runs[/{id}]` for status; temporary pages at `/ui/<domain>` (`include_in_schema=False`).
- **Queues**:
  - Workflow queue per workflow: `<workflow>-workflow`.
  - Activity queue per domain: `<domain>-activity`, with `-<mce>` appended when the limb writes to a cluster (`server-lifecycle-activity-<mce>`, `cluster-upgrade-activity-<mce>`, `upgrade-agent-activity-<mce>`).
  - A run with no worker on its queue waits, visible as a pending activity / `progress.activity_queue`.
- **Ids**: deterministic `<workflow>-<key>` (dedup gives 409), builders in `shared/workflow_ids.py`. Pool/slot ids `<workflow>-<mce>_<pool>_<1..100>`; `_` follows the MCE because it cannot appear in k8s names.
- **Names** (`shared/cluster_names.py`, `shared/infraenv_names.py`):
  - MCE `ocp4-<env>-mce-<site>-<letter>`, accepted with or without `ocp4-` and canonicalised at the edge.
  - InfraEnv `<conf>[-<letter>]-zone-<zone>-metal|<cpu>` (memory = cpu × 8 GiB).
  - Seed `ocp4-seed-<site>-<zone>`; KV clusters `ocp4-kubevirt-<site>-<zone>…`.
  - Servers `ocp-<infraEnv>…`.
  - HostedCluster `openshift-<clusterName>` / ns `hcp-<clusterName>`; clusterName = file name minus `ocp4-`.
  - Segment types `MCE|HC|INVENTORY|PXE`, allocation-time only.
- **Typing and validation**:
  - Every boundary uses pydantic models. Each `run()` takes ONE `*RunArgs` model.
  - **API-edge request models** (`*Request`, in the routers) are strict: `extra="forbid"`, constraints, field docs, validators.
  - History-decoded `*Input` models are lenient so replays don't wedge.
  - The edge models **are exposed as JSON Schema in `/openapi.json`** (OpenAPI 3.1 = JSON Schema 2020-12) with descriptions, defaults, min/max, patterns and enums. **A portal can auto-generate forms from `components.schemas.<X>Request`**, with caveats:
    - Cross-field and naming rules exist only server-side and surface as 422 `detail[{loc,msg,type}]`: `count` vs `server_names`, MCE/InfraEnv name parsing, IP normalization and region prefix, branch-name rules.
    - Progress and result are untyped in the OpenAPI.
    - Batch responses have no declared schema.
    - Dropdown sources (MCEs, InfraEnvs, sites, releases) are not in the schema. Wingman must supply them (it already has MCE/site/infraenv dropdowns), or use upgrade-targets for releases.
- **The 109 JSON files are NOT input schemas**:
  - 99 are Temporal golden histories for replay tests (`tests/histories/**`).
  - 6 are cluster-upgrade k8s fixtures (`tests/fixtures/cluster_upgrade/`).
  - 2 are wire contracts of external services: `tests/fixtures/kv_agents_contract.schema.json` and `upgrade_agent_contract.schema.json` (AgentRequest/AgentVerdict).
  - Plus `.claude/settings.json` and `skills-lock.json`.
- **Errors**: retries are unbounded; only classified errors fail a run (named exception classes in `shared/exceptions.py`). An unclassified permanent error leaves the run RUNNING with the failure on the pending activity. A UI should show "running, but activity failing".
- **Waits**: a machine wait has a deadline; a human wait has no deadline and uses continue-as-new. `CONTINUED_AS_NEW` rows appear in run lists.
- **Config**: env vars; ConfigMaps `workflows-orchestrator-config` (global: `TEMPORAL_HOST`, `TEMPORAL_NAMESPACE`, `SEGMENTS_MANAGER_URL`) plus `<domain>-config`; Secrets per limb. Temporal TLS for remote MCE workers goes through a passthrough Route (`deploy/hub/temporal-grpc-route.yaml`).
- **Commits**: conventional commits (same as Wingman). Conventions are enforced by `scripts/check_conventions.py`, run by a hook, pytest and CI.

---

## 5. Integration points for Wingman

**Position**: Wingman is the natural **"ClickCluster Platform UI"**. The workflows repo explicitly expects one, and its two `/ui/*` pages are placeholders for it.

1. **Server-side proxy.** Add an orchestrator client in Wingman's backend: a small FastAPI router in day1 (or a new service), or Next.js route handlers. Point it at `workflows-orchestrator-api.redbull-workflows.svc:8080`. Do not call from the browser (no CORS, no auth).
   - Gate every POST with Wingman's `AdminUser`, every GET with `CurrentUser`.
   - Fill `by` / `requested_by` from the JWT user.
   - Ask the workflows team to lock the Route or put an oauth-proxy in front. Today anyone reaching it can start a release-segment, which DELETEs a DHCP scope. (Per Wingman's CLAUDE.md, do not add NetworkPolicies.)
2. **Forms from OpenAPI.** Fetch `/openapi.json` (cache it with a long `staleTime`) and render forms from `components.schemas.*Request`. Overlay Wingman's own dropdown data (MCE, site, InfraEnv, cluster list) and show 422 `detail` per field. A per-workflow allowlist keeps dangerous routes, such as release-segment, out of the general UI.
3. **Run views.**
   - Poll `GET /workflows/runs/{id}` (React Query `refetchInterval` ~10 s while RUNNING, then stop).
   - List via `GET /workflows/runs?workflow_type=<Class>`, filtered client-side by id prefix.
   - Map per-workflow phase strings to labels (lists in §1a). Show `progress.activity_queue` when a run is stuck, and `error` (it contains the error type name).
   - Link out to the Temporal UI for history (its route was not found in this sandbox).
4. **Cluster page**:
   - "Upgrade" uses upgrade-targets for the version dropdown, then the upgrade-cluster POST.
   - Decision buttons for admins: approve / continue (NodePool) / confirm-day2 / pause / resume / abort / retry / action approve/reject.
   - Render `progress.plan`, `waiting_for`, `pending_actions` and `log`.
   - Show 409 refusals verbatim.
5. **MCE / inventory page**:
   - add-server-to-mce (`count` or `server_names`), remove-server-from-mce, uninstall-server-from-hc, publish-infraenv-to-pxe-server, create-vm, provision-dell-server. The last two need their limbs deployed first.
   - Show herzi-started runs too (same types).
6. **Day1: Wingman can fill the gap now. Design it so the planned workflow can take over.**
   - Today, Wingman's "render template + open MR" IS step 5 of §3a.
   - Align Wingman's output with the real day1 repo: `gitops-day1-platform-config`, path `sites/<site>/mces/<mce>/hostedClusters/<cluster>.yaml`, keys as in §3a, layered values.
   - Let the day1 pipeline call allocate-segment as it does now. Wingman should **not** allocate VLANs, write `vlanId`/`dhcp_values`, or call the Segments Manager, server-scan or the MCE itself.
   - Wingman's branch names (`platform/{user}/…`) pass allocate-segment's ref validation: slashes are fine; leading `-`, `..`, spaces and `~^:?*[\` are refused.
   - **Show** the `allocate-segment-HC-<cluster>` run on the MR/cluster page. Optionally show HostedCluster status after the merge; nothing in workflows provides that wait yet.
   - When `create-cluster` / `create-hosted-cluster` lands, Wingman switches from "write git + open MR" to "POST the workflow with the same form data". The workflow then owns the composition, segment, commit and post-merge waits. Keep Wingman's day1 renderer behind an adapter so that swap is cheap.
   - Open decisions to settle with the workflows team: who renders the cluster file (Wingman's Jinja specs vs a workflow "composing" step), who picks the hub/MCE (the spec's open question #1, which Wingman's MCE dropdown answers today), and whether the merge stays manual (Wingman's MR flow).
7. **Delete cluster**: today it is a Wingman MR deleting the file. Argo's PostDelete hook runs release-segment; Wingman can show `release-segment-HC-<cluster>`. Later this moves to POST deprovision-cluster.
8. **Day2**: no addon workflows exist here. Wingman's day2 service stays its own. See the gitops-day2-prod notes; cluster-upgrade reads day2 layers and has `confirm-day2`.
9. **Asks for the workflows team**:
   - auth on the API;
   - a list endpoint filtered by search attribute or id prefix (e.g. cluster) with paging;
   - a workflow-type catalog endpoint;
   - a generic cancel;
   - typed progress/result schemas in the OpenAPI;
   - an idempotency key on pool routes (double-clicks).
