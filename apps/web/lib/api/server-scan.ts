/**
 * day1's Server Scan routes (docs/notes/2026-11-13-server-scan-area-api.md,
 * ADR-0048): typed calls, query keys and hooks. Admins only;
 * `501 FEATURE_DISABLED` when server-scan is not configured, which the area
 * treats as "off".
 */

import { useQuery } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api-client";
import { useMounted } from "@/hooks/use-mounted";
import { useIsAdmin } from "@/stores/auth-store";
import type { SiteStatsList } from "@/types/server-scan";
import type { ServerRowsAnswer } from "@/types/server-scan-servers";

/**
 * As server-scan's own UI (its query client's `staleTime`): the Sites page is
 * read when it opens, and again when it is opened after 30 seconds. It is not
 * polled; server-scan's Servers page is.
 */
const SITES_STALE_MS = 30_000;
/** How long the top bar trusts that the area is on before asking again. */
const AREA_STALE_MS = 5 * 60_000;
/**
 * As server-scan's Servers page: the fleet is read every 30 seconds, in the
 * background too. An unchanged fleet is a bodiless 304 (day1's ETag, answered
 * by the browser's own cache), and structural sharing keeps every row.
 */
const SERVERS_POLL_MS = 30_000;

const serverScanKeys = {
  sites: ["server-scan", "sites"] as const,
  /** Never persisted to localStorage (`components/layout/providers.tsx`): 2 MB, polled. */
  servers: ["server-scan", "servers"] as const,
};

const serverScanApi = {
  sites: () => api.get<SiteStatsList>("/api/day1/server-scan/sites"),
  servers: () => api.get<ServerRowsAnswer>("/api/day1/server-scan/servers"),
};

/** A problem is day1's answer (403 for a viewer, 501 when off, 502 when server-scan fails): show it. Else once more, as server-scan's UI. */
const retryUnlessProblem = (count: number, error: unknown) => !isApiError(error) && count < 1;

/** server-scan's sites and fleet; also how the top bar learns whether the area is on. */
export function useServerScanSites({ enabled = true, staleTime = SITES_STALE_MS } = {}) {
  return useQuery<SiteStatsList>({
    queryKey: serverScanKeys.sites,
    queryFn: serverScanApi.sites,
    staleTime,
    retry: retryUnlessProblem,
    enabled,
  });
}

/**
 * Whether this person has the Server Scan area: an admin, with server-scan
 * configured. `undefined` while that is being found out; a failing
 * server-scan still counts as on (the page shows the failure).
 */
export function useServerScanArea(): boolean | undefined {
  const admin = useIsAdmin();
  const mounted = useMounted();
  const sites = useServerScanSites({ enabled: admin && mounted, staleTime: AREA_STALE_MS });
  if (!mounted) return undefined;
  if (!admin) return false;
  if (sites.isPending) return undefined;
  return !(isApiError(sites.error, "FEATURE_DISABLED") || isApiError(sites.error, "FORBIDDEN"));
}

/** server-scan's whole fleet, as rows, for the Servers page (§8.3); polled every 30 seconds. */
export function useServerScanServers() {
  return useQuery<ServerRowsAnswer>({
    queryKey: serverScanKeys.servers,
    queryFn: serverScanApi.servers,
    refetchInterval: SERVERS_POLL_MS,
    refetchIntervalInBackground: true,
    staleTime: 0,
    retry: retryUnlessProblem,
  });
}
