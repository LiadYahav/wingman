// ── MCE placement (docs/notes/2026-11-12-mce-placement-api.md, ADR-0050) ─────

/** A placement check: the version, the free pods, the servers of each node type, whether Wingman could read the MCE. */
export interface PlacementCheck {
  check: "version" | "free_pods" | "servers" | "readable";
  /** `not_checked`: live MCE reads are off; it does not block the pick. */
  status: "pass" | "fail" | "unknown" | "not_checked";
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
  /** `false` when live MCE reads are off: free pods and servers were not checked, `pods` is null, `node_types` empty. */
  live_reads: boolean;
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
