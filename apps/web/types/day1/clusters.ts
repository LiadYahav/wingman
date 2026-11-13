import type { PlacementChoice } from "./placement";

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
  /**
   * While upgrades are on, the newest release the cluster's MCE offers above
   * its mastertag (ADR-0034's list); `null` when none is, or upgrades are off.
   * A suggestion: the upgrade-cluster workflow plans the path (ADR-0055).
   */
  upgrade_available: string | null;
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
