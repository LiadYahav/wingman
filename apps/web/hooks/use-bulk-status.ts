import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { day1Keys } from "@/lib/api/day1";
import { fetchBulkStatus, type BulkStatusItem, type LiveStatuses } from "@/lib/live-status";
import type { ClusterStatus } from "@/types";

/**
 * Live status of every listed cluster in one request (the dashboard and the
 * cluster list share the cache entry). `data` is `null` when status is off.
 * A viewer's clusters have no MCE (ADR-0068): each is sent by its name, and
 * day1 reads its folder from the tree.
 */
export function useBulkStatus(clusters: ClusterStatus[] | undefined) {
  const input = useMemo(
    () => (clusters ?? []).map((c): BulkStatusItem => (c.mce ? { name: c.name, mce: c.mce } : { name: c.name })),
    [clusters]
  );
  return useQuery<LiveStatuses>({
    queryKey: day1Keys.clusters.bulkStatus(input),
    queryFn: () => fetchBulkStatus(input),
    enabled: input.length > 0,
    staleTime: 2 * 60_000,
    refetchInterval: (query) => (query.state.data === null ? false : 2 * 60_000),
    retry: false,
  });
}
