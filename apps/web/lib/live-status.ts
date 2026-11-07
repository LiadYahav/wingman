/**
 * Live HostedCluster status from the MCE hubs. It is off unless the day1
 * service runs with CLUSTER_STATUS_ENABLED; then every status route answers
 * 501 FEATURE_DISABLED, which the app shows as "status is off", not an error.
 */

import { api, isApiError } from "@/lib/api-client";
import type { ClusterLiveStatus, ClusterPhase } from "@/types";

/** `null` when live status is off in this deployment. */
export type LiveStatuses = Record<string, ClusterLiveStatus> | null;

/** `bulk-status`: every requested cluster answers, with `error` set when its read failed. */
export async function fetchBulkStatus(clusters: { name: string; mce: string }[]): Promise<LiveStatuses> {
  try {
    return await api.post<Record<string, ClusterLiveStatus>>("/api/day1/clusters/bulk-status", { clusters });
  } catch (error) {
    if (isApiError(error, "FEATURE_DISABLED")) return null;
    throw error;
  }
}

/** One cluster's status; `null` when live status is off. */
export async function fetchLiveStatus(name: string, mce: string): Promise<ClusterLiveStatus | null> {
  try {
    return await api.get<ClusterLiveStatus>(
      `/api/day1/clusters/${encodeURIComponent(name)}/status?mce=${encodeURIComponent(mce)}`
    );
  } catch (error) {
    if (isApiError(error, "FEATURE_DISABLED")) return null;
    throw error;
  }
}

export function liveStatusToPhase(s: ClusterLiveStatus): ClusterPhase {
  if (s.error) return "Error";
  if (s.hc_problems.length > 0) return "Error";
  if (s.node_pools.length === 0) return "Unknown";
  const allReady = s.node_pools.every(
    (np) => np.ready_replicas === np.desired_replicas && np.problems.length === 0
  );
  return allReady ? "Ready" : "Provisioning";
}
