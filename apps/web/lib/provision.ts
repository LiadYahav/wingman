/**
 * Creating a cluster: every create starts the platform's provision-cluster
 * workflow (docs/notes/2026-11-12-provision-cluster-workflow-api.md, ADR-0042).
 * Wingman only starts the run and shows it: the workflow reserves the segment,
 * opens the merge request and waits for it, and its phases are its own.
 */

import { useQuery } from "@tanstack/react-query";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { isRunning } from "@/lib/nodes";
import type { ProvisionRun } from "@/types";

/** How often a running provision run is read again. */
const PROVISION_POLL_MS = 10_000;

/** `GET /clusters/{name}/provision-run`, read again every 10 s while it runs. */
export function useProvisionRun(name: string, initial?: ProvisionRun) {
  return useQuery<ProvisionRun>({
    queryKey: day1Keys.clusters.provisionRun(name),
    queryFn: () => day1Api.clusters.provisionRun(name),
    initialData: initial,
    initialDataUpdatedAt: 0,
    refetchInterval: (query) => (isRunning(query.state.data) ? PROVISION_POLL_MS : false),
    retry: false,
  });
}
