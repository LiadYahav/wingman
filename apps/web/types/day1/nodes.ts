import type { WorkflowRun } from "./workflows";

// ── Cluster nodes by NodePool, and node uninstall (ADR-0038) ────────────────
//
// docs/notes/2026-11-11-cluster-nodes-api.md: the NodePools and Machines come
// from the cluster's MCE (read-only, as live status reads it); each Machine is
// followed to its server, and server-scan adds the link and the health.

/** server-scan's overall verdict on a server; `UNKNOWN` is not a verdict. */
export type NodeHealth = "HEALTHY" | "WARNING" | "MAJOR" | "CRITICAL" | "UNKNOWN";

/** server-scan's record of a server. */
export interface ServerRecord {
  /** server-scan's server id: the uninstall route names the server by it, and Wingman's server page is `/server-scan/servers/<id>`. */
  id: string;
  name: string;
  /** The server's page in server-scan's UI, where the name links for anyone without the Server Scan area. */
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
