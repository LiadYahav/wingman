import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchBulkStatus, type LiveStatuses } from "@/lib/live-status";
import type { ClusterStatus } from "@/types";

/**
 * Live status of every listed cluster in one request (the dashboard and the
 * cluster list share the cache entry). `data` is `null` when status is off.
 */
export function useBulkStatus(clusters: ClusterStatus[] | undefined) {
  const input = useMemo(
    () => (clusters ?? []).map((c) => ({ name: c.name, mce: c.mce })),
    [clusters]
  );
  return useQuery<LiveStatuses>({
    queryKey: ["clusters", "bulk-status", input],
    queryFn: () => fetchBulkStatus(input),
    enabled: input.length > 0,
    staleTime: 2 * 60_000,
    refetchInterval: (query) => (query.state.data === null ? false : 2 * 60_000),
    retry: false,
  });
}
