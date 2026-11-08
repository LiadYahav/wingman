// Types of the day1 service (`/api/day1`), from its Pydantic schemas in
// apps/day1-service/src/wingman_day1/api/v1/schemas.py. Every web-visible
// change is listed in docs/notes/2026-11-07-day1-api-changes.md.

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
      immutable_paths: string[];
      /** The shared cluster-template.j2, filled on read; never stored in the spec. */
      template: string;
      /** Preset template inputs, merged under what the create form sends. */
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

/** What the chart renders: `openshift-<clusterName>` in `hcp-<clusterName>` (ADR-0015). */
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
  /** The MCE's values.yaml mastertag: the create form's OCP version default. */
  default_mastertag: string | null;
  hub_version: string | null;
  cluster_count: number;
  /** Files in hostedClusters/ that break the MCE's ApplicationSet. */
  stray_files: string[];
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

/** `GET /clusters/{name}/drift`. */
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
