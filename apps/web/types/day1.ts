// Types of the day1 service (`/api/day1`), from its Pydantic schemas in
// apps/day1-service/src/wingman_day1/api/v1/schemas.py. Every web-visible
// change is listed in docs/notes/2026-11-07-day1-api-changes.md and, for
// flavors v2, docs/notes/2026-11-08-flavors-v2-api-changes.md ("§n" below).

// ── Template schema (parsed from the Jinja2 AST by the backend) ─────────────

export interface TemplateField {
  name: string;
  type: "string" | "integer" | "boolean" | "list" | "object";
  required: boolean;
  default?: unknown;
  example?: string;
  fields?: TemplateField[]; // sub-fields for list-of-objects
}

// ── Cluster spec ────────────────────────────────────────────────────────────

/** A legacy declared variable; new specs leave the list empty. */
export interface SpecVariable {
  name: string;
  type: "string" | "integer" | "boolean" | "list" | "object";
  required?: boolean;
  default?: unknown;
  description?: string;
  pattern?: string | null;
  enum?: string[] | null;
  minimum?: number | null;
  maximum?: number | null;
}

export interface OverrideableField {
  path: string;
  type: "string" | "integer" | "boolean" | "object" | "array";
  default?: unknown;
  description?: string;
}

export interface SpecAddon {
  team: string;
  name: string;
  version: string;
  overrideable: OverrideableField[];
}

export interface ClusterSpec {
  apiVersion: string;
  kind: string;
  metadata: {
    name: string;
    description?: string;
    version: string;
    labels?: Record<string, string>;
  };
  spec: {
    day1: {
      variables: SpecVariable[];
      structure: Record<string, unknown>;
      /**
       * Template-input paths whose value in `values` is fixed (§5, §6, ADR-0026):
       * `owner_anaf`, `nodepools[0].configs`, or the rule `nodepools[*].configs`
       * (§9, ADR-0029). Every other value in `values` is a preset.
       */
      locked_paths: string[];
      /** The shared cluster-template.j2, filled on read; never stored in the spec. */
      template: string;
      /** Template inputs: presets, and the locked values (`locked_paths`). */
      values?: Record<string, unknown>;
      /** One whole number per nodepool: they grow together, `ratio[i] * size` replicas (ADR-0040). */
      nodepool_ratio?: number[];
    };
    day2: {
      addons: SpecAddon[];
    };
  };
}

/** `GET /clusters/name-suggestion`: a free name for a new cluster from a flavor (ADR-0040). */
export interface NameSuggestion {
  /** `ocp4-<env>-<flavor>-<site>-<letter>`; `null` when there is none (`problems` says why). */
  name: string | null;
  env: string | null;
  short_name: string;
  sequence: string | null;
  problems: string[];
}

/** A spec as `GET /specs` lists it: a file that does not parse carries `load_error`. */
export interface SpecEntry extends ClusterSpec {
  load_error?: string | null;
  load_problems?: string[];
  /** Rules the stored flavor breaks: it loads, but saving it unchanged is refused (§5). */
  warnings?: string[];
  /** The `locked_paths` a create enforces (§5); a lock that breaks the rules is not in it. */
  enforced_locks?: string[];
}

// ── Machine configs (§1, §3, ADR-0027) ──────────────────────────────────────

/**
 * A nodepool's `configs` entry: a static config by name, or the cluster's own
 * network config `{name: "nm-conf", hardware}`, which day1 writes to the file
 * as `nm-conf-<clusterName>-<hardware>`. `hardware` belongs only to `nm-conf`.
 */
export interface ConfigEntry {
  name: string;
  hardware?: string | null;
}

/** A file under `mc-files/` (never `legacy/`); `folder` is `""` for the root. */
export interface StaticConfig {
  name: string;
  folder: string;
  path: string;
}

/** A network template `mc-files/templates/nm-conf-template-<name>.bu`, or the generic `nm-conf-template.bu`. */
export interface HardwareType {
  name: string;
  template: string;
  /** `generic`: for any hardware, written as plain `nm-conf`; listed first. */
  generic: boolean;
}

/** The specs repo's `nodepool-defaults.yaml`: the configs a new nodepool starts with. */
export interface NodepoolDefaults {
  path: string;
  /** `false`: there is no such file; no defaults, not an error. */
  found: boolean;
  /** `nm-conf` may leave out its hardware: the nodepool picks it. */
  configs: ConfigEntry[];
  /** Set when the file exists but cannot be used; `configs` is then empty. */
  error: string | null;
  /** Why some default entries would not resolve, or why the file is unusable. */
  problems: string[];
}

/** `GET /api/day1/machine-configs` (any session). */
export interface MachineConfigs {
  /** Always `"nm-conf"`. */
  network_config: string;
  static_configs: StaticConfig[];
  hardware_types: HardwareType[];
  nodepool_defaults: NodepoolDefaults;
  /** Files in `mc-files/` that are not offered, and why (for admins). */
  problems: string[];
}

/** `GET /specs/{name}`: one spec, with the commit its file was read at. */
export interface SpecDetail extends SpecEntry {
  /**
   * Send it back on update and delete (`?last_commit_id=`); a stale one is
   * 409 REVISION_CONFLICT (ADR-0006). Optional: a day1 service that predates
   * it does not send it, and a write then goes unguarded.
   */
  last_commit_id?: string | null;
}

/** A commit of `GET /specs/{name}/history`. */
export interface SpecCommit {
  sha: string;
  short_sha: string;
  message: string;
  author: string;
  date: string;
  web_url: string;
}

// ── Naming and the HostedCluster a file renders ─────────────────────────────

/** Whether a name follows `ocp4-<env>-<name>-<site>[-<seq>]` (ADR-0014). */
export interface ClusterNaming {
  follows_convention: boolean;
  env: string | null;
  short_name: string | null;
  sequence: string | null;
  problems: string[];
}

/** What the chart renders: `ocp4-<clusterName>` in `hcp-<clusterName>` (ADR-0015). */
export interface HostedClusterRef {
  cluster_name: string;
  name: string;
  namespace: string;
}

// ── Sites and MCEs (read-only, ADR-0018) ────────────────────────────────────

export interface Mce {
  name: string;
  site: string;
  env: string | null;
  letter: string | null;
  follows_convention: boolean;
  naming_problems: string[];
  /** The MCE's values.yaml mastertag: the create form's OCP version default, when the MCE offers it. */
  default_mastertag: string | null;
  hub_version: string | null;
  cluster_count: number;
  /** Files in hostedClusters/ that break the MCE's ApplicationSet. */
  stray_files: string[];
  problems: string[];
}

/** `GET /api/day1/mces/{mce}/openshift-versions` (ADR-0034). */
export interface OpenShiftVersions {
  mce: string;
  /** The upgrade ladder's releases in the minors the MCE can host, newest first, bare (`4.20.44`). */
  versions: string[];
  /** Why `versions` is short or empty: a missing or broken file under the day1 repo's `upgrade/`. */
  problems: string[];
}

// ── MCE placement (docs/notes/2026-11-12-mce-placement-api.md, ADR-0050) ─────

/** A placement check: the version, the free pods, the servers of each node type, whether Wingman could read the MCE. */
export interface PlacementCheck {
  check: "version" | "free_pods" | "servers" | "readable";
  status: "pass" | "fail" | "unknown";
  /** One sentence in plain words. */
  detail: string;
}

/** What the new cluster needs of one node type (an InfraEnv): its nodepools' replicas, summed. */
export interface PlacementNeed {
  infra_env: string;
  replicas: number;
}

/** One node type's part of a candidate's `servers` check. */
export interface PlacementNodeType {
  infra_env: string;
  needed: number;
  /** `null` when the MCE's Agents could not be read. */
  free_agents: number | null;
  /** `null` when server-scan could not be read, or is not configured. */
  healthy: number | null;
  /** Free Agents server-scan has no server for. */
  not_in_server_scan: number;
  status: "pass" | "fail" | "unknown";
  /** E.g. "dell-r660: 4 healthy free of 3 needed". */
  detail: string;
}

/** The pods an MCE has free, counted on its workers: Ready, schedulable, untainted, neither control-plane nor infra. */
export interface PlacementPods {
  /** Never below 0. */
  free: number;
  allocatable: number;
  used: number;
  nodes_counted: number;
  /** Each left-out node once, by the first reason: control-plane, infra, not Ready, cordoned, tainted. */
  nodes_excluded: { control_plane: number; infra: number; not_ready: number; unschedulable: number; tainted: number };
}

/** One candidate MCE: its numbers, its checks, and where it ranks. */
export interface PlacementCandidate {
  mce: string;
  /** Every check passes. */
  eligible: boolean;
  /** `rank === 1`. */
  picked: boolean;
  /** 1-based among the eligible; `null` for the rest. */
  rank: number | null;
  /** For an eligible candidate that is not the pick: the first ranking step the pick beats it on. */
  behind_on: "owner_clusters" | "clusters" | "spare_servers" | "name" | null;
  /** Always the four, in this order: version, free_pods, servers, readable. */
  checks: PlacementCheck[];
  /** One entry per need: the servers of that node type this MCE has free for it. */
  node_types: PlacementNodeType[];
  /** The releases this MCE hosts, newest first. */
  versions: string[];
  /** Cluster files plus open create merge requests. */
  clusters: number;
  /** How many of `clusters` are open create merge requests. */
  open_creates: number;
  /** `null` without an owner. */
  owner_clusters: number | null;
  /** `null` when unknown (`spare_detail` says why). */
  spare: { total: number; usable: number } | null;
  spare_detail: string | null;
  /** `null` when the MCE could not be read. */
  pods: PlacementPods | null;
}

/** `GET /api/day1/placement?site=&env=&version=&owner=&flavor=`: Wingman's pick and every candidate. */
export interface Placement {
  site: string;
  env: string;
  version: string | null;
  owner: string | null;
  flavor: string | null;
  min_free_pods: number;
  /** The summed needs the `servers` check used, by InfraEnv; empty when no nodepool names a node type yet. */
  needs: PlacementNeed[];
  /** Every version some candidate hosts, newest first. */
  versions: string[];
  /** `null` when no candidate passes every check (`problems` says why). */
  pick: string | null;
  /** Why the pick won, in one sentence; `null` without a pick. */
  why: string | null;
  problems: string[];
  /** Why every MCE's spare servers are unknown, when they are. */
  server_scan_error: string | null;
  /** The eligible by rank, then the others by name. */
  candidates: PlacementCandidate[];
}

/** What a create sends about the MCE: the pick the form showed, and the reason for another choice. */
export interface PlacementChoice {
  pick: string | null;
  /** Required only when `mce` is not the pick; 1 to 500 characters. */
  reason: string | null;
}

// ── Clusters ────────────────────────────────────────────────────────────────

export type ClusterPhase = "Provisioning" | "Ready" | "Error" | "Deleting" | "Unknown";

/** A row of `GET /clusters`. Unparsable and off-convention files are listed, flagged. */
export interface ClusterStatus {
  name: string;
  site: string;
  mce: string;
  /** Always `Unknown`: live state comes from the status endpoints. */
  phase: ClusterPhase;
  /** `null` when the cluster is not linked to a spec. */
  spec_name: string | null;
  spec_version: string | null;
  /** Author and date of the file's last change. */
  created_by: string | null;
  created_at: string | null;
  mastertag: string | null;
  path: string;
  hosted_cluster: HostedClusterRef;
  naming: ClusterNaming;
  /** The file's owner numbers as text (`{merkaz, anaf, mador}`); `{}` when it has none (§13). */
  owner: Record<string, string>;
  /** Why the file does not parse; empty when it does. */
  problems: string[];
}

export interface NodePoolValues {
  name: string | null;
  infra_env_name: string | null;
  replicas: number | null;
  allow_deletion: unknown;
  configs: string[];
  node_labels: Record<string, unknown>;
  tuning_config: unknown;
}

/** `vlanId` and `dhcp_values.network`: written by the allocate-segment workflow. */
export interface ClusterNetwork {
  vlan_id: unknown;
  dhcp_network: string | null;
  /** `dhcp_values.network` as its /24; `null` until it is written, or when it is not a /24's network address. */
  segment: string | null;
}

/** segments-manager's record of the cluster's segment. */
export interface SegmentLedgerRecord {
  vlan_id: number | null;
  /** A list for a shared `UPI` segment; `null` while it is Available. */
  cluster_name: string | string[] | null;
  status: string | null;
  type: string | null;
  site: string | null;
}

/** `GET /clusters/{name}/network`: the file's network, the EPG from segments-manager, and what disagrees. */
export interface ClusterNetworkRead {
  vlan_id: number | null;
  segment: string | null;
  /** `null` when segments-manager is off, failed, or has no such segment. */
  epg: string | null;
  ledger: SegmentLedgerRecord | null;
  problems: string[];
  /** Why segments-manager could not be read; the file's values stand regardless. */
  ledger_error: string | null;
}

/** What the cluster file sets. */
export interface ClusterValues {
  owner: Record<string, unknown> | null;
  mastertag: string | null;
  platform: string;
  nodepools: NodePoolValues[];
  network: ClusterNetwork;
  /** An explicit `clusterName` key, if the file has one. */
  cluster_name: string | null;
  /** Keys automation owns (`vlanId`, `dhcp_values`, `mcFiles`, `mcConfigMap`); an edit keeps them. */
  automation_keys: string[];
}

export interface RequestedAddon {
  team: string;
  name: string;
  version: string;
  override_values: Record<string, unknown>;
}

export interface ClusterMetadata {
  spec_name: string | null;
  spec_version: string | null;
  created_by: string;
  created_at: string | null;
  site: string;
  mce: string;
  /** Always empty: the inputs of a render are not stored. */
  variables: Record<string, unknown>;
  immutable_paths: string[];
  requested_addons: RequestedAddon[];
}

/** `GET /clusters/{name}`. */
export interface ClusterDetail {
  name: string;
  site: string;
  mce: string;
  yaml: string;
  gitlab_url: string;
  path: string;
  /** Send it back with an edit or delete: a stale one is 409 REVISION_CONFLICT. */
  last_commit_id: string;
  metadata: ClusterMetadata;
  /** `null` when the file does not parse (`problems` says why). */
  values: ClusterValues | null;
  hosted_cluster: HostedClusterRef;
  naming: ClusterNaming;
  mce_default_mastertag: string | null;
  problems: string[];
  /** `null` unless day1's `SEGMENTS_MANAGER_UI_URL` is set. */
  segments_manager: SegmentsManagerLinks | null;
}

/**
 * Links to segments-manager, built by day1. Its UI opens no single cluster,
 * so the page names the cluster (`ClusterDetail.name`, the file stem) to
 * search for there.
 */
export interface SegmentsManagerLinks {
  /** The UI. */
  url: string;
  /** `GET /api/segments/search?q=<name>`: the cluster's segment as JSON. */
  search_url: string;
}

/** `POST /clusters` and `POST /clusters/preview`. */
export interface CreateClusterRequest {
  name: string;
  site: string;
  mce: string;
  spec_name: string;
  spec_version: string;
  /** Template inputs; `openshift_release_version` is required. */
  variables: Record<string, unknown>;
  /** Override values per spec addon, keyed `"<team>/<name>"`. */
  addon_overrides?: Record<string, Record<string, unknown>>;
  /** With MCE placement on (ADR-0050): the pick the form showed, and the reason for choosing another MCE. */
  placement?: PlacementChoice;
}

export interface ClusterPreview {
  yaml: string;
  path: string;
}

/** `PATCH /clusters/{name}`. */
export interface ModifyClusterRequest {
  updated_yaml: string;
  change_summary?: string;
  last_commit_id?: string;
}

// ── Live status (off unless CLUSTER_STATUS_ENABLED) ─────────────────────────

export interface NodePoolStatus {
  name: string;
  ready_replicas: number;
  desired_replicas: number;
  /** A failed in-place update is one; an update rolling through is not (it is `updating`). */
  problems: string[];
  /** `version`, `config` or `machine_template` while an update rolls through the pool. */
  updating?: string | null;
}

export interface ClusterLiveStatus {
  cluster_name: string;
  /** The HostedCluster that was read, and its namespace. */
  hosted_cluster: string;
  namespace: string;
  hc_phase: string | null;
  ocp_version: string | null;
  hc_problems: string[];
  node_pools: NodePoolStatus[];
  /** Set when this cluster's status could not be read. */
  error: string | null;
}

// ── Drift ───────────────────────────────────────────────────────────────────

/** `unknown`: day2 did not answer or the spec is gone (`error` says which). */
export type DriftState = "in_sync" | "drifted" | "unknown" | "not_linked";

/** A spec addon the cluster does not have: the drift. The fix installs it at the team default. */
export interface AddonDrift {
  addon_name: string;
  team: string;
  reason: "missing";
  expected_version: string;
  /** The values requested at create; install with them. */
  override_values: Record<string, unknown>;
}

/** A spec addon installed at another version: information, never drift (ADR-0025). */
export interface VersionDifference {
  addon_name: string;
  team: string;
  spec_version: string;
  installed_version: string;
}

/** A nodepool of the cluster file: its position and the NodePool the chart renders. */
export interface NodepoolRef {
  index: number;
  name: string;
}

/** A locked value the cluster file does not hold (§10, ADR-0036). */
export interface ValueDrift {
  /** The flavor's lock: `owner_anaf`, `nodepools[0].configs` or the rule `nodepools[*].configs`. */
  path: string;
  /** Where the file holds it: `owner.anaf`, `nodepool[1].configs`. */
  file_key: string;
  nodepool: NodepoolRef | null;
  /** The locked value in the file's form; `nm-conf` expanded where the nodepool's hardware is known. */
  flavor_value: unknown;
  /** What the file holds; `null` with `in_file: false` when the key is absent. */
  cluster_value: unknown;
  in_file: boolean;
  /** Configs only: the names a sync adds. */
  added: string[];
  /** Configs only: the names a sync removes. */
  removed: string[];
  /** Why a sync cannot set this value until a person decides; `null` when it can. */
  needs_decision: string | null;
  /** The decision is the nodepool's network hardware type: a sync request can choose it. */
  needs_hardware: boolean;
  /** A nodepool's configs: syncing them rolls its nodes. */
  reboots: boolean;
}

/** `GET /clusters/{name}/drift`. Drifted: a locked value differs, or an add-on is missing. */
export interface ClusterDrift {
  cluster: string;
  site: string;
  mce: string;
  state: DriftState;
  /** `null` when unknown. */
  is_drifted: boolean | null;
  spec_name: string | null;
  spec_version: string | null;
  current_spec_version: string | null;
  value_drift: ValueDrift[];
  addon_drift: AddonDrift[];
  version_differences: VersionDifference[];
  error: string | null;
}

/** A row of `GET /clusters/drift-summary`. */
export interface DriftSummaryItem {
  name: string;
  site: string;
  mce: string;
  state: DriftState;
  is_drifted: boolean | null;
  error: string | null;
}

/** A row of `GET /specs/{name}/clusters`. */
export interface SpecCluster {
  name: string;
  site: string;
  mce: string;
  phase: string;
  state: DriftState;
  is_drifted: boolean | null;
  error: string | null;
}

/** A row of `GET /specs/{name}/drift`. */
export interface SpecDrift {
  cluster: string;
  site: string;
  mce: string;
  state: DriftState;
  is_drifted: boolean | null;
  spec_version: string | null;
  error: string | null;
}

// ── Import existing clusters into a flavor (§11, ADR-0037) ──────────────────

/** A cluster to compare with a flavor; `site` and `mce` only when the name is ambiguous. */
export interface ClusterPick {
  name: string;
  site?: string | null;
  mce?: string | null;
}

/** `POST /specs/{name}/import/preview` body (up to 500 clusters). */
export interface ImportPreviewRequest {
  clusters: ClusterPick[];
}

/** `ready`: no flavor yet; `relink`: follows another; `linked`: follows this one; `refused`: can't be edited. */
export type ImportStatus = "ready" | "relink" | "linked" | "refused";

export interface ImportCandidate {
  name: string;
  site: string;
  mce: string;
  path: string;
  /** Send it back with the import. */
  last_commit_id: string;
  status: ImportStatus;
  /** The flavor the file follows now. */
  linked_spec: { name: string; version: string | null } | null;
  /** Why it cannot be imported as it is (empty for `ready`). */
  problems: string[];
  /** The cluster against this flavor: what will show as drift once it is linked. */
  drift: ClusterDrift;
}

/** `POST /specs/{name}/import/preview`. */
export interface ImportPreview {
  spec_name: string;
  /** Send it back with the import. */
  spec_version: string;
  /** About the flavor: positional nodepool locks compare whichever nodepool is there. */
  warnings: string[];
  clusters: ImportCandidate[];
}

/** One cluster of `POST /specs/{name}/import`, as the preview returned it. */
export interface ImportPick {
  name: string;
  site: string;
  mce: string;
  last_commit_id: string;
  /** `true` to move a cluster that follows another flavor to this one. */
  relink?: boolean;
}

/** `POST /specs/{name}/import` body: one day1 MR, at most 50 clusters. */
export interface ImportRequest {
  spec_version: string;
  clusters: ImportPick[];
}

// ── Sync a cluster to its flavor (§12, ADR-0037) ────────────────────────────

/** A person's network hardware choice for a nodepool whose own can't be read. */
export interface HardwareChoice {
  nodepool: number;
  hardware: string;
}

/** `POST /clusters/{name}/sync/preview` body. */
export interface SyncPreviewRequest {
  hardware?: HardwareChoice[];
}

/** A config the sync removes; each must be confirmed. */
export interface ConfigRemoval {
  nodepool: NodepoolRef;
  name: string;
}

/** A nodepool whose configs change: merging rolls its nodes. */
export interface Rebooting {
  nodepool: NodepoolRef;
  replicas: number | null;
  /** `null` when unset: the chart's `InPlace` (drain and reboot). */
  upgrade_type: string | null;
  /** `inPlace.maxUnavailable`; `null`: one node at a time. */
  max_unavailable: number | string | null;
  /** `upgradeType: Replace`: new nodes are provisioned and the old ones removed. */
  replaces_nodes: boolean;
}

/** `POST /clusters/{name}/sync/preview`. */
export interface SyncPreview {
  cluster: string;
  site: string;
  mce: string;
  path: string;
  /** Send it back with the sync. */
  last_commit_id: string;
  spec_name: string;
  /** The flavor's current version; send it back with the sync. */
  spec_version: string;
  /** The version the file's header names now. */
  file_spec_version: string | null;
  /** Every locked value the file does not hold, with the hardware choices applied. */
  changes: ValueDrift[];
  /** The cluster file change as a unified diff; empty when nothing changes. */
  diff: string;
  removals: ConfigRemoval[];
  rebooting: Rebooting[];
  /** Why the sync can't run now; `can_sync` is then false. */
  problems: string[];
  /** Worth checking before merging; they don't block. */
  warnings: string[];
  can_sync: boolean;
  /** Not in the day1 MR: install them through day2 (one MR per team). */
  addons_to_install: AddonDrift[];
  version_differences: VersionDifference[];
  /** Set when day2 did not answer: missing add-ons are unknown. */
  addons_error: string | null;
}

/** `POST /clusters/{name}/sync` body: what the preview showed, the removals confirmed. */
export interface SyncRequest {
  last_commit_id: string;
  spec_version: string;
  hardware?: HardwareChoice[];
  /** Exactly the preview's `removals`, or the sync is refused. */
  confirm_removals: { nodepool: number; name: string }[];
}

// ── The delete-cluster workflow (ADR-0033) ──────────────────────────────────

/** One run of a workflow that acts on a cluster, as the orchestrator reports it. */
export interface WorkflowRun {
  workflow_id: string;
  /** The orchestrator's status, lowercase: `running`, `completed`, `failed`, ... */
  status: string;
  /** The step it is on, for example `awaiting-prune`. */
  phase: string | null;
  error: string | null;
}

/**
 * A provision-cluster run (ADR-0042): `POST /clusters` in workflow mode (202),
 * and `GET /clusters/{name}/provision-run`. The phase is the workflow's own
 * word; Wingman keeps no list of them.
 */
export interface ProvisionRun extends WorkflowRun {
  /** The new cluster file's stem. */
  cluster: string;
  /** The merge request the workflow opened, once it has. */
  merge_request_url: string | null;
  merge_request_state: string | null;
}

/** `GET /clusters/provisioner`: what Create does in this deployment. */
export interface Provisioner {
  mode: "merge-request" | "workflow";
}

/** `GET /clusters/{name}/delete-workflow` (501 FEATURE_DISABLED until the workflow exists). */
export interface DeleteWorkflowState {
  run: WorkflowRun | null;
}

// ── Cluster nodes by NodePool, and node uninstall (ADR-0038) ────────────────
//
// docs/notes/2026-11-11-cluster-nodes-api.md: the NodePools and Machines come
// from the cluster's MCE (read-only, as live status reads it); each Machine is
// followed to its server, and server-scan adds the link and the health.

/** server-scan's overall verdict on a server; `UNKNOWN` is not a verdict. */
export type NodeHealth = "HEALTHY" | "WARNING" | "MAJOR" | "CRITICAL" | "UNKNOWN";

/** server-scan's record of a server. */
export interface ServerRecord {
  /** server-scan's server id: the uninstall route names the server by it. */
  id: string;
  name: string;
  /** The server's page in server-scan's UI. */
  url: string;
  serial: string | null;
  vendor: string | null;
  model: string | null;
  site: string;
  mce: string | null;
  /** server-scan's `openshift_state`: `INSTALLED`, `INSTALLED_TO_INVENTORY`, `AVAILABLE`. */
  state: string;
  health: NodeHealth;
  maintenance: boolean;
  reachable: boolean;
  stale: boolean;
  /** Two clusters' jobs claim the server. Shown only: the workflow refuses such a server itself. */
  contested: boolean;
  last_seen_at: string | null;
}

/**
 * What day1 derives for a Machine, in this order: `deleting`, `failed`,
 * `waiting` (no Agent reserved), `installing`, `joining` (no Node yet),
 * `not_ready`, `ready`. `missing` is not a Machine: the pool wants more than
 * it has, and one such row stands for each one short.
 */
export type NodeState = "deleting" | "failed" | "waiting" | "missing" | "installing" | "joining" | "not_ready" | "ready";

/** The Agent behind a Machine: its `debugInfo.state` and `progress.currentStage`. */
export interface NodeAgent {
  name: string;
  state: string | null;
  stage: string | null;
}

/** One Machine of a NodePool, or a missing one, with the server it leads to. */
export interface PoolNode {
  /** `null` on a `missing` row. */
  machine: string | null;
  node_name: string | null;
  state: NodeState;
  /** The node an update is working on right now. */
  current: boolean;
  /** What is happening to it now, in words ("Draining", "Rebooting for the update (…)"). */
  activity: string | null;
  /** Why a `waiting` (or `missing`) row waits. */
  waiting_for: string | null;
  /** Replace only: a Machine of an older revision, which the rollout will replace. `null` for InPlace. */
  outdated: boolean | null;
  agent: NodeAgent | null;
  /** The BareMetalHost name, server-scan's server name; `null` without an Agent. */
  server_name: string | null;
  /** `null` when server-scan has no record of it, or is not configured or not answering. */
  server: ServerRecord | null;
  /** The server's newest uninstall run (the 202's shape), or `null`. `phase` is the workflow's own string. */
  uninstall: WorkflowRun | null;
}

/** An update of a NodePool in progress: `UpdatingVersion`, `UpdatingConfig` or `UpdatingPlatformMachineTemplate`. */
export interface NodePoolUpdate {
  kind: "version" | "config" | "machine_template";
  /** The condition's own text. */
  message: string | null;
  /** From "Total Nodes: n. Upgraded: k", when an in-place update says it. */
  progress: { total: number; updated: number } | null;
  /** `InplaceUpgradeFailed`. */
  failed: boolean;
}

/** A NodePool of the cluster, as the MCE reports it. */
export interface NodePoolNodes {
  name: string;
  /** `spec.replicas`; `null` when it autoscales. */
  wanted: number | null;
  autoscaling: { min: number; max: number } | null;
  /** `status.replicas`. */
  ready: number;
  /** The version it last finished updating to. */
  version: string | null;
  upgrade_type: "InPlace" | "Replace" | null;
  /** Its `agentLabelSelector` in words. */
  agent_selector: string | null;
  update: NodePoolUpdate | null;
  /** Its `Ready`, `AllMachinesReady` and `AllNodesHealthy` conditions that are not True, as "<Type>: <reason>: <message>". */
  problems: string[];
  /** The Agents matching its selector, and how many are free; `null` when they could not be counted. */
  free_agents: { matching: number; free: number } | null;
  /** By state (`failed` first, `ready` last), then by name. */
  nodes: PoolNode[];
}

/** A server server-scan places in the cluster that no Machine leads to (for a while after an uninstall). */
export interface UnassignedServer extends ServerRecord {
  uninstall: WorkflowRun | null;
}

/** Whether this deployment can start an uninstall; `detail` says why not. */
export interface UninstallAvailability {
  available: boolean;
  detail: string | null;
}

/** `GET /clusters/{name}/nodes` (501 FEATURE_DISABLED when live status is off: the MCE cannot be read). */
export interface ClusterNodes {
  hosted_cluster: string;
  /** Sorted by name. */
  node_pools: NodePoolNodes[];
  /** Empty when `server_scan_error` is set. */
  unassigned: UnassignedServer[];
  uninstall: UninstallAvailability;
  /** server-scan could not be read: every `server` is `null`, so no links or health. */
  server_scan_error: string | null;
  /** The orchestrator could not be read: every `uninstall` is `null`, and run states are unknown. */
  runs_error: string | null;
}

/** `POST /clusters/{name}/nodes/{server_id}/uninstall` body: the server's name typed again. Answers 202 with a `WorkflowRun`. */
export interface UninstallNodeRequest {
  server_name: string;
}
