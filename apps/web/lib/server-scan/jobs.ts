/**
 * The Jobs page's decisions and words, as server-scan's page makes them
 * (docs/notes/2026-11-13-server-scan-area-api.md §14.1): how often the list
 * and an open log are read, whether a Job is unfinished, a card's line when
 * it has no Job, a pod's button, a manual run's words and the log's caption;
 * and why Run job is off, and its confirmation's words.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/features/jobs/JobsPage.tsx` (`TAIL`,
 * `LIST_POLL_MS`, `LOG_POLL_MS`, `isUnfinished` and the page's words).
 */

import type { CronJob, JobPod, JobRun, JobState, JobsOverview, PodLogs } from "@/types/server-scan-jobs";
import { formatTimestamp } from "./datetime";

/** The lines a log shows, as server-scan's page always asks for. */
export const LOG_TAIL = 500;
/** The list while any CronJob has an unfinished Job; six times slower otherwise. */
export const LIST_POLL_MS = 5_000;
/** An open log while its Job is unfinished. */
export const LOG_POLL_MS = 3_000;

export const NO_CRONJOBS = "No triggerable CronJobs found.";
export const FEATURE_OFF = "Running jobs from the UI is not enabled on this deployment.";
export const ENABLED_HINT = "The `enabled` flag for this job in the deployment's values.yaml";
/** The confirmation's words: what Run job starts. */
export const RUN_WORDS = "It starts a real Job from the CronJob's template and runs exactly as scheduled.";
/** A card's line after a start that was sent and not answered (Wingman's; server-scan's page has none). */
export const UNCONFIRMED_START =
  "The last start was not answered: a run may have started. Look at the runs below before starting it again.";

/** The open log: which pod of which Job of which CronJob. */
export interface SelectedPod {
  cronjob: string;
  job: string;
  pod: string;
}

/** Every 5 seconds while a Job runs somewhere, every 30 otherwise (and before the first answer). */
export function jobsPollMs(overview: JobsOverview | undefined): number {
  return overview?.cronjobs.some((c) => c.active) ? LIST_POLL_MS : LIST_POLL_MS * 6;
}

/** Whether a state is a Job still going: running, or created and not started. */
function isUnfinishedState(state: JobState): boolean {
  return state === "active" || state === "pending";
}

/** Whether the selected pod's Job is still running, read from the latest list. */
export function isUnfinished(cronjobs: CronJob[] | undefined, selected: SelectedPod): boolean {
  const job = cronjobs?.find((c) => c.name === selected.cronjob)?.jobs.find((j) => j.name === selected.job);
  return job !== undefined && isUnfinishedState(job.state);
}

/** Why Run job is off for this CronJob (its tooltip), as server-scan's; `null` when it can run. */
export function runBlocked(cronjob: CronJob): string | null {
  if (!cronjob.deployed) return "Not deployed: turn it on in values.yaml first";
  if (cronjob.active) return "A Job of this CronJob is already running";
  return null;
}

/** The new Job's first pod, whose log opens after a start; none yet: nothing opens. */
export function startedPod(cronjob: string, job: JobRun): SelectedPod | null {
  const pod = job.pods[0];
  return pod ? { cronjob, job: job.name, pod: pod.name } : null;
}

/** A card's line in place of its Jobs. */
export function noRunsText(cronjob: CronJob): string {
  return cronjob.deployed ? "No Jobs yet." : "Not deployed: it is switched off in values.yaml.";
}

/** `enabled: true`, the CronJob's values.yaml flag, as server-scan's pill says it. */
export function enabledLabel(cronjob: CronJob): string {
  return `enabled: ${String(cronjob.enabled)}`;
}

/** A pod's button: `Logs · abcde · Succeeded`, the pod name's last five characters. */
export function podButtonLabel(pod: JobPod): string {
  return `Logs · ${pod.name.slice(-5)} · ${pod.phase}`;
}

/** "by hand (api-token-admin)" for a Job started by hand; `null` for a scheduled one. */
export function manualText(job: JobRun): string | null {
  if (!job.manual) return null;
  return job.triggered_by ? `by hand (${job.triggered_by})` : "by hand";
}

/** The log's caption: its tail, and that it refreshes while the Job runs. */
export function logsCaption(active: boolean): string {
  return `Last ${LOG_TAIL} lines${active ? ", refreshing every 3 s while the job runs" : ""}.`;
}

/** What the log shows: the text, "(no output yet)" for none, "Loading…" before the first answer. */
export function logsBody(logs: PodLogs | undefined): string {
  if (!logs) return "Loading…";
  return logs.text || "(no output yet)";
}

/** The intro's last words: server-scan's own simulated jobs say so. */
export function backendNote(overview: JobsOverview | undefined): string | null {
  return overview?.backend === "fake" ? "This deployment uses simulated jobs." : null;
}

function line(label: string, at: string | null): string | null {
  return at ? `${label} ${formatTimestamp(at)}` : null;
}

/** The schedule's tooltip: when it last fired and last succeeded (server-scan's page does not show them). */
export function scheduleHint(cronjob: CronJob): string {
  const lines = [line("Last scheduled", cronjob.last_schedule_time), line("Last succeeded", cronjob.last_successful_time)];
  const known = lines.filter((l) => l !== null);
  return known.length > 0 ? known.join("\n") : "It has not run yet.";
}

/** A Job's time's tooltip: created, started and finished, the ones known. */
export function runTimesHint(job: JobRun): string {
  return [line("Created", job.created_at), line("Started", job.started_at), line("Finished", job.finished_at)]
    .filter((l) => l !== null)
    .join("\n");
}
