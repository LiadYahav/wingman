// ── Upgrading a cluster through the upgrade-cluster workflow (ADR-0055) ─────
//
// docs/notes/2026-11-13-upgrade-cluster-workflow-api.md §3. Phases, reasons,
// texts and outcomes are the workflow's own strings, passed through: none of
// them is a closed list here.

/** One target `GET .../upgrade-targets` offers: a ladder rung newer than the mastertag. */
export interface UpgradeTarget {
  version: string;
  minor: string;
  /** Steps of the plan to it, control plane and workers. */
  steps: number;
  control_plane_steps: number;
  /** The newest rung of its minor: the recommended pick for that minor. */
  newest_in_minor: boolean;
  must: boolean;
}

/** A NodePool as the workflow reads it from the cluster file. */
export interface UpgradeTargetNodePool {
  name: string;
  /** `null` when the NodePool follows the mastertag. */
  workertag: string | null;
  upgrade_type: string | null;
  zone: string | null;
  replicas: number | null;
  /** The file's `inPlace.maxUnavailable` (`"1"`, `"33%"`); `null` when unset. */
  max_unavailable: string | null;
}

/** `GET /clusters/{name}/upgrade-targets`. An empty `targets` is an answer: nothing newer. */
export interface UpgradeTargets {
  cluster: string;
  mce: string;
  mce_version: string;
  /** The file's mastertag, as the workflow read it. */
  control_plane_version: string | null;
  supported_minors: string[];
  ladder_revision: string;
  /** When the ladder was last checked against the upgrade graph. */
  verified_against_graph: string | null;
  targets: UpgradeTarget[];
  nodepools: UpgradeTargetNodePool[];
  /** The default roll order. */
  nodepool_order: string[];
}

/** `POST /clusters/{name}/upgrade`: exactly one of the targets; day1 adds the cluster and who asked. */
export interface StartUpgradeRequest {
  target_version?: string;
  target_minor?: string;
  nodepool_order?: string[];
  max_unavailable?: Record<string, number | string>;
  workers_to_target?: boolean;
  nodepool_mode?: "manual" | "auto";
  auto_approve?: boolean;
}

/** One step of the run's plan: the control plane, or NodePools, to `version`. */
export interface UpgradePlanStep {
  /** `control-plane` or `workers` today. */
  kind: string;
  version: string;
  /** Why the plan has it (`ladder`, `target`, `skew`, ...), the workflow's word. */
  reason: string;
  nodepools: string[];
}

export interface UpgradePlan {
  control_plane: string;
  target: string;
  max_worker_skew: number | null;
  /** Each NodePool's version when the plan was made. */
  nodepools: Record<string, string>;
  steps: UpgradePlanStep[];
}

/** An action the upgrade agent proposed, and what became of it. */
export interface UpgradePendingAction {
  action_id: string;
  kind: string;
  target: string;
  args: Record<string, string>;
  rationale: string;
  /** `pending`, `approved` or `rejected`. */
  decision: string;
  decided_by: string | null;
  executed: boolean;
  result: string | null;
}

/** The upgrade agent's last conclusion. */
export interface UpgradeVerdict {
  diagnosis: string;
  confidence: string;
  verdict: string;
}

export interface UpgradeLogLine {
  at: string;
  event: string;
  by: string | null;
  detail: string;
}

/** `GET /clusters/{name}/upgrade-run`: the cluster's newest upgrade run. */
export interface UpgradeRun {
  workflow_id: string;
  cluster: string;
  /** Lowercase: `running` while the run is open, then `completed`, `failed`, ... */
  status: string;
  /** The workflow's own word; `null` before the first read and once completed. */
  phase: string | null;
  /** What has to happen next, in the workflow's words. */
  waiting_for: string | null;
  mce: string | null;
  plan: UpgradePlan | null;
  profile: string | null;
  current_step: number | null;
  current_nodepool: string | null;
  nodepools_done: string[];
  control_plane_version: string | null;
  nodepool_versions: Record<string, string>;
  max_unavailable: Record<string, string>;
  paused: boolean;
  pending_actions: UpgradePendingAction[];
  last_verdict: UpgradeVerdict | null;
  verified_against_graph: string | null;
  /** Oldest first, as the workflow keeps it (its last 20 lines). */
  log: UpgradeLogLine[];
  /** Once completed: `done`, `cancelled` or `aborted`. */
  outcome: string | null;
  steps_completed: number | null;
  error: string | null;
  /** The decisions the run accepts now, once the workflow reports them; `null` until then. */
  decisions: string[] | null;
}

/** A person's decision on a run (`POST .../upgrade-run/{decision}`). */
export type UpgradeDecision =
  | "approve"
  | "approve-admin-ack"
  | "continue"
  | "confirm-day2"
  | "pause"
  | "resume"
  | "abort"
  | "retry";

/** `reason` is required for abort and approve-admin-ack; `nodepool` is for continue only. */
export interface UpgradeDecisionRequest {
  reason?: string;
  nodepool?: string;
}

/** 200 to a decision: the run took it; `run` is `null` when it could not be read again. */
export interface UpgradeDecisionResult {
  workflow_id: string;
  decision: string;
  run: UpgradeRun | null;
}

/**
 * One cluster's newest upgrade run, for the clusters list's "Upgrading" rows
 * (`GET /api/day1/upgrades`, open runs first). Strings are the workflow's.
 */
export interface FleetUpgrade {
  workflow_id: string;
  /** The cluster file's stem. */
  cluster: string;
  /** Where day1 has the file; `null` when it has none (or several). */
  site: string | null;
  mce: string | null;
  /** Lowercase: `running` while the upgrade is open. */
  status: string;
  /** When the upgrade's first segment started. */
  started_at: string | null;
  closed_at: string | null;
  /** The workflow's own word; `null` once closed, or when day1 did not read the run (only the first rows are). */
  phase: string | null;
  waiting_for: string | null;
  paused: boolean;
  /** Once completed: `done`, `cancelled` or `aborted`. */
  outcome: string | null;
}

/** `GET /api/day1/upgrades`. */
export interface FleetUpgrades {
  runs: FleetUpgrade[];
}
