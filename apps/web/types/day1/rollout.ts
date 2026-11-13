import type { MergeRequestLink } from "./drift";

// ── A flavor's rollout: one MR per cluster (ADR-0044) ───────────────────────
//
// docs/notes/2026-11-12-flavor-rollout-api.md §2: a new flavor version opens,
// for every cluster that follows the flavor on an older version, one day1 MR
// that syncs it; the customer merges theirs when ready.

/**
 * Where a cluster that follows the flavor stands with its newest version:
 * - `on_version`: its header is on it;
 * - `merge_request_open`: an open MR syncs it to it (`merge_request`);
 * - `pending`: an MR will open (the next run, or the one running);
 * - `needs_decision`: no MR opens until a person syncs it by hand (`reasons`);
 * - `declined`: its MR for the version was closed without merging (`merge_request`);
 * - `failed`: this replica's last attempt failed (`reasons`); the next run tries again;
 * - `unknown`: its file cannot be read (`reasons`).
 */
export type RolloutState =
  | "on_version"
  | "merge_request_open"
  | "pending"
  | "needs_decision"
  | "declined"
  | "failed"
  | "unknown";

/** One cluster of a rollout. */
export interface RolloutCluster {
  name: string;
  site: string;
  mce: string;
  path: string;
  /** The version its header names now. */
  from_version: string | null;
  state: RolloutState;
  /** The MR for the version: open (`merge_request_open`) or closed (`declined`). */
  merge_request: MergeRequestLink | null;
  reasons: string[];
}

/** What started a reconcile: the flavor MR's merge, the specs webhook, Reconcile now, or a read with work pending. */
export type RolloutTrigger = "merge" | "webhook" | "reconcile" | "read";

/** This replica's last run for the flavor. */
export interface RolloutRun {
  trigger: RolloutTrigger;
  started_at: string;
  /** `null` while the run is still going. */
  finished_at: string | null;
  opened: number;
  failed: number;
}

/**
 * `GET /specs/{name}/rollout` (any session), and `POST` (admins: Reconcile
 * now, 202 with the same body). The rollout of the flavor's newest version.
 */
export interface RolloutStatus {
  spec_name: string;
  /** The flavor's newest version; `null` (and `clusters` empty) when the flavor cannot be read. */
  version: string | null;
  /** This replica is opening MRs now: read again until it is not. */
  running: boolean;
  last_run: RolloutRun | null;
  counts: Record<RolloutState, number>;
  clusters: RolloutCluster[];
}

/** A cluster a flavor MR's merge touches. */
export interface RolloutClusterRef {
  name: string;
  site: string;
  mce: string;
}

/** A nodepool whose nodes roll when the cluster's MR merges. */
export interface RollingNodepool {
  name: string;
  replicas: number | null;
  /** `upgradeType: Replace`: new nodes are provisioned and the old ones removed. */
  replaces_nodes: boolean;
  /** `inPlace.maxUnavailable`; `null`: one node at a time. */
  max_unavailable: number | string | null;
}

/**
 * `GET /approvals/{iid}/rollout?repo=specs` (any session): what merging a
 * flavor MR will open, before it is merged. Merging it is the one
 * confirmation; each cluster MR repeats what it does to its cluster.
 */
export interface ApprovalRollout {
  /** `false` (with `reason`) for an MR that gives no existing flavor a new version. */
  applies: boolean;
  reason: string | null;
  spec_name: string;
  /** The version the MR gives the flavor. */
  version: string | null;
  /** main's version. */
  current_version: string | null;
  /** The clusters that follow the flavor. */
  following: number;
  /** The cluster MRs merging opens. */
  opens: number;
  already_on_version: number;
  needs_decision: (RolloutClusterRef & { reasons: string[] })[];
  rolls_nodes: (RolloutClusterRef & { nodepools: RollingNodepool[] })[];
  removes_configs: (RolloutClusterRef & { removals: { nodepool: string; name: string }[] })[];
  /** `<team>/<name>`: the add-ons the MR's version lists and main's does not. */
  adds_addons: string[];
}
