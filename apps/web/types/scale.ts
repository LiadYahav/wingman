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
  /**
   * The entry's `redbull.io/scale-down-policy` annotation as written (`fewest-pods`, `least-requested`,
   * `least-utilized`; the workflow refuses any other), which picks the nodes a scale-down removes; `null`
   * without one: CAPI picks at random.
   */
  scale_down_policy: string | null;
}

/** `GET /clusters/{name}/scale`: what Scale can change on this cluster, from its day1 file and flavor. */
export interface ScaleOptions {
  cluster: string;
  mce: string | null;
  flavor: string | null;
  nodepools: ScaleNodePool[];
}

/** `POST /clusters/{name}/scale` body: one NodePool of the day1 file, by name, and its own replicas, set exactly. */
export interface StartScaleRequest {
  nodepool: string;
  replicas: number;
  /** A scale-down only, optional: exactly the servers that leave (each node's `machine_server`), as many as it removes. */
  server_names?: string[];
  /**
   * A scale-down only, optional, never with `server_names`: this run's policy (`fewest-pods`, `least-requested`,
   * `least-utilized`), ranked ahead of the NodePool's own.
   */
  scale_down_policy?: string;
}

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
  /** The policy the run applied: this run's, else the NodePool's own; `null`: none (named servers, or CAPI at random). */
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
  /** The policy's name; `named` for a server the request named. */
  policy: string;
  /** The policy's reading: `1 workload pods`, `requested 41%`, `no Node`, `NotReady`; `named: <name>`. */
  reason: string;
  /** The server, lowercased, when the request named it; else `null`. */
  server: string | null;
}

/** What a completed run did. */
export interface ScaleResult {
  /** Only on a run recorded by InfraEnv kind before 2026-11-18 (a total over the kind's NodePools); else `nodepool`. */
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
  /** What the request said about a scale-down that this run (up, or no change) had no use for: never a failure. */
  ignored: string[];
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
