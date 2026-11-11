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
    };
    day2: {
      addons: SpecAddon[];
    };
  };
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

/** A network template `mc-files/templates/nm-conf-template-<name>.bu`. */
export interface HardwareType {
  name: string;
  template: string;
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
  problems: string[];
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

/** `GET /clusters/{name}/delete-workflow` (501 FEATURE_DISABLED until the workflow exists). */
export interface DeleteWorkflowState {
  run: WorkflowRun | null;
}
