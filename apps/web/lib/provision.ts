/**
 * Creating a cluster through the platform's provision-cluster workflow
 * (docs/notes/2026-11-12-provision-cluster-workflow-api.md, ADR-0042). Wingman
 * only starts the run and shows it: the workflow reserves the segment, opens
 * the merge request and waits for it, and its phases are its own.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { isRunning } from "@/lib/nodes";
import type { MRDetail, ProvisionRun, Provisioner } from "@/types";

/** How often a running provision run is read again. */
export const PROVISION_POLL_MS = 10_000;

/** What Create does here; `merge-request` until day1 says otherwise. */
export function useProvisioner() {
  return useQuery<Provisioner>({
    queryKey: ["clusters", "provisioner"],
    queryFn: () => api.get<Provisioner>("/api/day1/clusters/provisioner"),
    staleTime: 5 * 60_000,
  });
}

/** A create's answer: the started run in workflow mode, the merge request otherwise. */
export function isProvisionRun(result: MRDetail | ProvisionRun): result is ProvisionRun {
  return "workflow_id" in result;
}

/** `GET /clusters/{name}/provision-run`, read again every 10 s while it runs. */
export function useProvisionRun(name: string, initial?: ProvisionRun) {
  return useQuery<ProvisionRun>({
    queryKey: ["clusters", name, "provision-run"],
    queryFn: () => api.get<ProvisionRun>(`/api/day1/clusters/${encodeURIComponent(name)}/provision-run`),
    initialData: initial,
    initialDataUpdatedAt: 0,
    refetchInterval: (query) => (isRunning(query.state.data) ? PROVISION_POLL_MS : false),
    retry: false,
  });
}
