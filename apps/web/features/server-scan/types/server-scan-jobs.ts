/**
 * The Server Scan area's Jobs page: server-scan's CronJobs, their runs and a
 * pod's log, which day1 passes through typed and in server-scan's own shapes
 * (docs/notes/2026-11-13-server-scan-area-api.md §15, ADR-0048's 3.32.0
 * amendment). server-scan keeps them for its admins, reads included, so day1
 * reads them with its admin token.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/api/jobs.ts`. `state` and `backend` keep
 * server-scan's words; a word it adds later is still a string.
 */

/** A Job's state, as server-scan judges it from the Job's status and conditions. */
export type JobState = "active" | "succeeded" | "failed" | "pending";

// ── GET /api/day1/server-scan/jobs (server-scan's GET /api/v1/jobs) ──────────

/** One pod of a Job. */
export interface JobPod {
  name: string;
  /** Kubernetes' pod phase: `Pending`, `Running`, `Succeeded`, `Failed`, `Unknown`. */
  phase: string;
  started_at: string | null;
}

/** One Job of a CronJob, scheduled or started by hand. */
export interface JobRun {
  name: string;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  active: number;
  succeeded: number;
  failed: number;
  state: JobState;
  manual: boolean;
  /** Who server-scan wrote on a Job started by hand: the caller's token (Wingman's), never the person. */
  triggered_by: string | null;
  /** Oldest first. */
  pods: JobPod[];
}

/** One CronJob server-scan may start, and its recent Jobs. */
export interface CronJob {
  name: string;
  schedule: string;
  suspend: boolean;
  last_schedule_time: string | null;
  last_successful_time: string | null;
  /** What running it can do (the chart's annotation), shown in the confirmation. */
  warning: string | null;
  /** It has an unfinished Job: server-scan refuses another start. */
  active: boolean;
  /** Its `enabled` flag in the deployment's values.yaml. */
  enabled: boolean;
  /** Whether the CronJob exists (one switched off in values.yaml does not). */
  deployed: boolean;
  /** Newest first. */
  jobs: JobRun[];
}

/** Whether server-scan lets its UI start Jobs, and the CronJobs, by name. */
export interface JobsOverview {
  enabled: boolean;
  backend: "kubernetes" | "fake" | "off";
  namespace: string | null;
  cronjobs: CronJob[];
}

// ── GET /api/day1/server-scan/jobs/{cronjob}/runs/{job}/pods/{pod}/logs ───────

/** The last lines of one pod's log. */
export interface PodLogs {
  pod: string;
  tail: number;
  text: string;
}
