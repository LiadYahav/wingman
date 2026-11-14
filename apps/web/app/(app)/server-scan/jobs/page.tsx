import { JobsPage } from "@/components/server-scan/jobs/jobs-page";

/**
 * The Server Scan area's Jobs page (ADR-0048's 3.32.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §15): server-scan's collector
 * and prune CronJobs, their runs and logs, for Wingman's admins.
 */
export default function Page() {
  return <JobsPage />;
}
