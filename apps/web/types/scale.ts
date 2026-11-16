// ── Scaling NodePools through the update-nodepool workflow (ADR-0062) ───────
//
// docs/notes/2026-11-16-scale-nodepools-api.md: behind DAY1_SCALE_NODEPOOLS
// (off: every route answers 501 FEATURE_DISABLED). Wingman starts the
// platform's update-nodepool run and shows it; the plan, the balance rule and
// the phases are the workflow's. Its strings are passed through as it gives
// them, so a phase or a field it adds needs no change here.

/** One `nodepool[]` entry of the cluster's day1 file, as Scale offers it. */
export interface ScaleNodePool {
  /** Its position in the file (`nodepool[i]`). */
  index: number;
  /** The NodePool the chart renders (`name`, else `<clusterName>-<infraEnvName>`); `null`: it cannot be named. */
  name: string | null;
  infra_env: string | null;
  /** The file's (1 when absent: the chart's default); `null` when it is not a number. */
  replicas: number | null;
  /** The flavor that locks this NodePool's replicas; it cannot be scaled to anything else. */
  locked_by: string | null;
  locked_replicas: number | null;
  /** Why it cannot be named (and so not scaled by name); `null` when it can. */
  unnamed: string | null;
}

/** A hardware kind: the NodePools of this cluster whose InfraEnv is it or starts with it and a dash. */
export interface ScaleKind {
  kind: string;
  /** The NodePools it selects, by name. */
  nodepools: string[];
  /** Their replicas now, added up; `null` when one is not a number. */
  total: number | null;
  /** The locked NodePools it selects: non-empty, it cannot be scaled. */
  locked: string[];
}

/** `GET /clusters/{name}/scale`: what Scale can change on this cluster, from its day1 file and flavor. */
export interface ScaleOptions {
  cluster: string;
  mce: string;
  flavor: string | null;
  nodepools: ScaleNodePool[];
  kinds: ScaleKind[];
}

/** `POST /clusters/{name}/scale` body: a total over a kind's NodePools, or one NodePool's own replicas. */
export type StartScaleRequest = { infra_env_kind: string; replicas: number } | { nodepool: string; replicas: number };

/** The child that scales (`scale-up-nodepool-<cluster>` or `scale-down-nodepool-<cluster>`), read by its own id. */
export interface ScaleChildRun {
  workflow_id: string;
  status: string | null;
  phase: string | null;
  error: string | null;
}

/** One NodePool the run planned: its replicas before and after. */
export interface ScaleNodePoolChange {
  name: string;
  infra_env: string | null;
  before: number | null;
  after: number | null;
  /** Its `redbull.io/scale-down-policy`; `null`: none, CAPI picks at random. */
  scale_down_policy: string | null;
}

/** A NodePool as the MCE showed it after the sync. */
export interface ScaleLiveReplicas {
  name: string;
  replicas: number | null;
  ready_replicas: number | null;
}

/** A server a scale-down chose to leave, and what put it first. */
export interface ScaleChosenServer {
  nodepool: string;
  machine: string;
  node: string | null;
  policy: string;
  /** The policy's reading: `1 workload pods`, `requested 41%`, `no Node`, `NotReady`. */
  reason: string;
}

/** What a completed run did. */
export interface ScaleResult {
  infra_env_kind: string | null;
  nodepool: string | null;
  day1_path: string | null;
  /** `none`: the replicas already were the request, nothing written. */
  direction: string;
  total_before: number | null;
  total_after: number | null;
  nodepools: ScaleNodePoolChange[];
  child_workflow_id: string | null;
  /** The day1 commit (main's head when `committed` is false: day1 already held it). */
  revision: string | null;
  committed: boolean | null;
  live: ScaleLiveReplicas[];
  chosen: ScaleChosenServer[];
  /** The marked Machines it saw deleting. */
  deleting: string[];
}

/** `GET /clusters/{name}/scale-run` (404: none yet), and the 202 of a start. */
export interface ScaleRun {
  workflow_id: string;
  /** The orchestrator's status, lowercase: `running`, `completed`, `failed`, `canceled`, ... */
  status: string;
  /** The workflow's own word: `reading-day1`, `planning`, `scaling-down`, ... */
  phase: string | null;
  direction: string | null;
  child: ScaleChildRun | null;
  result: ScaleResult | null;
  /** Why it failed, in the workflow's words. */
  error: string | null;
  /** The error's type when the words name one (`ArgoSyncRefusedError`). */
  error_type: string | null;
}

/**
 * A drifted locked replicas a flavor sync no longer writes (ADR-0062): it is
 * restored through update-nodepool, one run per cluster at a time.
 */
export interface HeldReplicas {
  index: number;
  name: string | null;
  replicas: number | null;
  flavor_replicas: number;
}
