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
