/**
 * day1's Jobs routes (docs/notes/2026-11-13-server-scan-area-api.md §14,
 * ADR-0048's 3.32.0 amendment): server-scan's CronJobs, their runs and a
 * pod's log, read through day1 with server-scan's admin token. Admins only,
 * as the area; `501` without the admin token (beside a viewer token) or
 * without server-scan, `404` for a CronJob, Job or pod server-scan does not
 * have. Read as server-scan's page reads them; never kept in the browser.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { retryUnlessProblem } from "@/lib/api/server-scan";
import { jobsPollMs, LOG_POLL_MS, LOG_TAIL, type SelectedPod } from "@/lib/server-scan/jobs";
import type { JobsOverview, PodLogs } from "@/types/server-scan-jobs";

const JOBS_PATH = "/api/day1/server-scan/jobs";

const serverScanJobsKeys = {
  /** Never persisted to localStorage (`components/layout/providers.tsx`): polled, and a run's state must be now. */
  all: ["server-scan", "jobs"] as const,
  logs: ({ cronjob, job, pod }: SelectedPod) => ["server-scan", "jobs", "logs", cronjob, job, pod] as const,
};

const logsPath = ({ cronjob, job, pod }: SelectedPod) =>
  `${JOBS_PATH}/${[cronjob, "runs", job, "pods", pod, "logs"].map(encodeURIComponent).join("/")}?tail=${LOG_TAIL}`;

/** server-scan's triggerable CronJobs and their runs: every 5 seconds while one runs, else every 30. */
export function useServerScanJobs() {
  return useQuery<JobsOverview>({
    queryKey: serverScanJobsKeys.all,
    queryFn: () => api.get<JobsOverview>(JOBS_PATH),
    refetchInterval: (query) => jobsPollMs(query.state.data),
    staleTime: 0,
    retry: retryUnlessProblem,
  });
}

/** A pod's last 500 lines; read again every 3 seconds while its Job is unfinished (`active`). */
export function useJobLogs(selected: SelectedPod, active: boolean) {
  return useQuery<PodLogs>({
    queryKey: serverScanJobsKeys.logs(selected),
    queryFn: () => api.get<PodLogs>(logsPath(selected)),
    refetchInterval: active ? LOG_POLL_MS : false,
    staleTime: 0,
    retry: retryUnlessProblem,
  });
}
