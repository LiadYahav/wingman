/**
 * day1's Segments routes (docs/notes/2026-11-13-segments-area-api.md):
 * typed calls, query keys and hooks. Admins only; `501 FEATURE_DISABLED`
 * when segments-manager is not configured, which the area treats as "off".
 */

import { useQuery } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api-client";
import { useMounted } from "@/hooks/use-mounted";
import { useIsAdmin } from "@/stores/auth-store";
import type { SegmentSites } from "@/types/segments";

const segmentsKeys = {
  sites: ["segments", "sites"] as const,
};

const segmentsApi = {
  sites: () => api.get<SegmentSites>("/api/day1/segments/sites"),
};

/** A problem is day1's answer (403 for a viewer, 501 when off): show it, don't ask again. */
const retryUnlessProblem = (count: number, error: unknown) => !isApiError(error) && count < 2;

/** The sites; also how the area switch learns whether the area is on. Read by admins only. */
function useSegmentSites({ enabled = true } = {}) {
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
