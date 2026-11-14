/**
 * The Jobs page's mocks (docs/notes/2026-11-13-server-scan-area-api.md §14),
 * typed so a shape change fails `tsc`: made-up CronJobs in server-scan's own
 * shapes, as its `JobsPage.test.tsx` makes them: a collector with a warning
 * and a failed run between two good ones, one running now (started by
 * hand), and one switched off in values.yaml.
 */

import type { Page, Route } from "@playwright/test";
import { json } from "./api-handlers";
import { setUpServerScan } from "./server-scan";
import type { CronJob, JobRun, JobsOverview, PodLogs } from "../../types/server-scan-jobs";

const HOUR = 3_600_000;
const ago = (ms: number) => new Date(Date.now() - ms).toISOString().replace(/\.\d+Z$/, "Z");

export const OPENMANAGE = "server-scan-collectors-collector-openmanage";
export const UCS = "server-scan-collectors-collector-ucs-central";
export const REDFISH = "server-scan-collectors-collector-redfish-standalone";
const IDRAC_WARNING = "This run can restart an iDRAC (ADR-0050) when a Dell has every disk or NIC UNKNOWN.";

function run(name: string, overrides: Partial<JobRun> = {}): JobRun {
  const state = overrides.state ?? "succeeded";
  const phase = { active: "Running", succeeded: "Succeeded", failed: "Failed", pending: "Pending" }[state];
  return {
    name,
    created_at: ago(2 * HOUR),
    started_at: ago(2 * HOUR),
    finished_at: state === "active" ? null : ago(HOUR),
    active: state === "active" ? 1 : 0,
    succeeded: state === "succeeded" ? 1 : 0,
    failed: state === "failed" ? 1 : 0,
    state,
    manual: false,
    triggered_by: null,
    pods: [{ name: `${name}-x7k2p`, phase, started_at: ago(2 * HOUR) }],
    ...overrides,
  };
}

function cronjob(name: string, overrides: Partial<CronJob> = {}): CronJob {
  return {
    name,
    schedule: "0 6 * * *",
    suspend: false,
    last_schedule_time: ago(2 * HOUR),
    last_successful_time: ago(HOUR),
    warning: null,
    active: false,
    enabled: true,
    deployed: true,
    jobs: [run(`${name}-29386440`)],
    ...overrides,
  };
}

export function overview(cronjobs: CronJob[], overrides: Partial<JobsOverview> = {}): JobsOverview {
  return { enabled: true, backend: "kubernetes", namespace: "server-scan", cronjobs, ...overrides };
}

export const JOBS: JobsOverview = overview([
  cronjob(OPENMANAGE, {
    warning: IDRAC_WARNING,
    jobs: [
      run(`${OPENMANAGE}-29386440`, { created_at: ago(2 * HOUR) }),
      run(`${OPENMANAGE}-29385720`, { state: "failed", created_at: ago(14 * HOUR) }),
      run(`${OPENMANAGE}-29384280`, { created_at: ago(26 * HOUR) }),
    ],
  }),
  cronjob(UCS, {
    active: true,
    jobs: [run(`${UCS}-manual-k3x9qa`, { state: "active", manual: true, triggered_by: "api-token-admin", created_at: ago(60_000) })],
  }),
  cronjob(REDFISH, { enabled: false, deployed: false, schedule: "", jobs: [], last_schedule_time: null, last_successful_time: null }),
]);

export const LOG_TEXT = "INFO collector.start\nINFO collector.done created=0 updated=12 unchanged=2492 errors=0\n";

type Handler = (route: Route) => Promise<void> | void;
const LOGS = /\/api\/day1\/server-scan\/jobs\/[^/]+\/runs\/[^/]+\/pods\/[^/]+\/logs\?/;
type Answer<T> = T | Handler;

/**
 * An admin, the Sites read the top bar makes, and day1's Jobs routes.
 * Returns how many times the list and the logs were read. Register a test's
 * own routes after this: mocks match LIFO.
 */
export async function setUpJobs(
  page: Page,
  { jobs = JOBS, logs = { pod: "", tail: 500, text: LOG_TEXT }, viewer = false, sites }: { jobs?: Answer<JobsOverview>; logs?: Answer<PodLogs>; viewer?: boolean; sites?: Handler } = {}
): Promise<{ reads: () => number; logReads: () => number }> {
  let reads = 0;
  let logReads = 0;
  await setUpServerScan(page, { viewer, ...(sites ? { sites } : {}) });
  await page.route("**/api/day1/server-scan/jobs", (route) => {
    reads += 1;
    return typeof jobs === "function" ? jobs(route) : json(route, jobs);
  });
  await page.route(LOGS, (route) => {
    logReads += 1;
    if (typeof logs === "function") return logs(route);
    const pod = new URL(route.request().url()).pathname.split("/").at(-2) ?? "";
    return json(route, { ...logs, pod });
  });
  return { reads: () => reads, logReads: () => logReads };
}
