/**
 * day1's Segments routes (docs/notes/2026-11-13-segments-area-api.md):
 * typed calls, query keys and hooks. Admins only; `501 FEATURE_DISABLED`
 * when segments-manager is not configured, which the area treats as "off".
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { api, isApiError } from "@/lib/api-client";
import { useMounted } from "@/hooks/use-mounted";
import { useIsAdmin } from "@/stores/auth-store";
import type { SegmentList, SegmentSites, SegmentStats } from "@/types/segments";

/** The page re-reads every 30 seconds while it is open, as segments-manager's UI does. */
export const SEGMENTS_REFRESH_MS = 30_000;

const segmentsKeys = {
  sites: ["segments", "sites"] as const,
  stats: ["segments", "stats"] as const,
  list: ["segments", "list"] as const,
};

const segmentsApi = {
  sites: () => api.get<SegmentSites>("/api/day1/segments/sites"),
  stats: () => api.get<SegmentStats>("/api/day1/segments/stats"),
  list: ({ fresh = false } = {}) => api.get<SegmentList>(`/api/day1/segments${fresh ? "?fresh=true" : ""}`),
};

/** A problem is day1's answer (403 for a viewer, 501 when off): show it, don't ask again. */
const retryUnlessProblem = (count: number, error: unknown) => !isApiError(error) && count < 2;

/** The sites; also how the area switch learns whether the area is on. Read by admins only. */
export function useSegmentSites({ enabled = true } = {}) {
  return useQuery<SegmentSites>({
    queryKey: segmentsKeys.sites,
    queryFn: segmentsApi.sites,
    staleTime: 5 * 60_000,
    retry: retryUnlessProblem,
    enabled,
  });
}

/**
 * Whether this person has the Segments area: an admin, with segments-manager
 * configured. `undefined` while that is being found out; a failing
 * segments-manager still counts as on (the page shows the failure).
 */
export function useSegmentsArea(): boolean | undefined {
  const admin = useIsAdmin();
  const mounted = useMounted();
  const sites = useSegmentSites({ enabled: admin && mounted });
  if (!mounted) return undefined;
  if (!admin) return false;
  if (sites.isPending) return undefined;
  return !(isApiError(sites.error, "FEATURE_DISABLED") || isApiError(sites.error, "FORBIDDEN"));
}

export function useSegmentStats() {
  return useQuery<SegmentStats>({
    queryKey: segmentsKeys.stats,
    queryFn: segmentsApi.stats,
    staleTime: 10_000,
    refetchInterval: SEGMENTS_REFRESH_MS,
    retry: retryUnlessProblem,
  });
}

export function useSegmentList() {
  return useQuery<SegmentList>({
    queryKey: segmentsKeys.list,
    queryFn: () => segmentsApi.list(),
    staleTime: 10_000,
    refetchInterval: SEGMENTS_REFRESH_MS,
    retry: retryUnlessProblem,
  });
}

/** A Refresh whose fresh read failed: when, and what. */
export interface RefreshFailure {
  at: number;
  error: unknown;
}

/**
 * The Refresh button: the list read fresh from segments-manager's database
 * (day1 allows one such read per few seconds per replica, and says so in
 * `fresh`), then the cards. Resolves to the fresh list; throws what failed,
 * and keeps it as `failed` (for the connection dot) until a Refresh succeeds.
 */
export function useRefreshSegments() {
  const client = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const [failed, setFailed] = useState<RefreshFailure | null>(null);
  const refresh = useCallback(async (): Promise<SegmentList> => {
    setRefreshing(true);
    try {
      const list = await segmentsApi.list({ fresh: true }).catch((error: unknown) => {
        setFailed({ at: Date.now(), error });
        throw error;
      });
      setFailed(null);
      client.setQueryData(segmentsKeys.list, list);
      await client.refetchQueries({ queryKey: segmentsKeys.stats, exact: true });
      return list;
    } finally {
      setRefreshing(false);
    }
  }, [client]);
  return { refresh, refreshing, failed };
}
