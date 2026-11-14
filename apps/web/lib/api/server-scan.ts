/**
 * day1's Server Scan routes (docs/notes/2026-11-13-server-scan-area-api.md,
 * ADR-0048): typed calls, query keys and hooks. Admins only;
 * `501 FEATURE_DISABLED` when server-scan is not configured, which the area
 * treats as "off".
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api-client";
import { useMounted } from "@/hooks/use-mounted";
import { useIsAdmin } from "@/stores/auth-store";
import type { SiteStatsList } from "@/types/server-scan";
import type { AuditEventPage, ServerRecord, VmHostAnswer } from "@/types/server-scan-record";
import type { MaintenanceAnswer, MaintenanceStart, ServerRowsAnswer } from "@/types/server-scan-servers";

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
/**
 * As server-scan's query client: a server's page is read when it opens, and
 * again when it is opened after 30 seconds; it is not polled (§9.1).
 */
const RECORD_STALE_MS = 30_000;
/** A History page, as server-scan's: 50 events, newest first. */
const HISTORY_PAGE_SIZE = 50;

const serverScanKeys = {
  sites: ["server-scan", "sites"] as const,
  /** Never persisted to localStorage (`components/layout/providers.tsx`): 2 MB, polled. */
  servers: ["server-scan", "servers"] as const,
  /** A server's page; its VM host and History sit below it, so dropping it drops them. */
  server: (id: string) => ["server-scan", "server", id] as const,
  vmHost: (id: string) => ["server-scan", "server", id, "vm-host"] as const,
  history: (id: string) => ["server-scan", "server", id, "history"] as const,
};

const serverPath = (id: string) => `/api/day1/server-scan/servers/${encodeURIComponent(id)}`;

const serverScanApi = {
  sites: () => api.get<SiteStatsList>("/api/day1/server-scan/sites"),
  servers: () => api.get<ServerRowsAnswer>("/api/day1/server-scan/servers"),
  server: (id: string) => api.get<ServerRecord>(serverPath(id)),
  vmHost: (id: string) => api.get<VmHostAnswer>(`${serverPath(id)}/vm-host`),
  history: (id: string, cursor: string) => {
    const query = new URLSearchParams({ page_size: String(HISTORY_PAGE_SIZE) });
    if (cursor) query.set("cursor", cursor);
    return api.get<AuditEventPage>(`${serverPath(id)}/events?${query}`);
  },
  maintenance: (id: string, start: MaintenanceStart | null) => {
    const path = `${serverPath(id)}/maintenance`;
    return start ? api.put<MaintenanceAnswer>(path, start) : api.del<MaintenanceAnswer>(path);
  },
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

/** One server into maintenance (`start`, with its reason and expected end) or out of it (`null`). */
interface MaintenanceVariables {
  id: string;
  start: MaintenanceStart | null;
}

/**
 * A server's maintenance on or off (§8.5), behind day1's admin check. Never
 * retried (ADR-0006): an unanswered change is `AMBIGUOUS_WRITE`. As
 * server-scan's own hook: the row (and the server's page) is patched from
 * the answer at once, then the rows, the Sites counts and the server's page
 * (its History too) are read again; after a failure too, so they show what
 * server-scan has.
 */
export function useMaintenanceChange() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, start }: MaintenanceVariables) => serverScanApi.maintenance(id, start),
    retry: false,
    onSuccess: (answer) => {
      client.setQueryData<ServerRowsAnswer>(serverScanKeys.servers, (data) =>
        data ? { ...data, items: data.items.map((row) => (row.id === answer.id ? { ...row, maintenance: answer.maintenance } : row)) } : data
      );
      client.setQueryData<ServerRecord>(serverScanKeys.server(answer.id), (record) =>
        record ? { ...record, maintenance: { ...record.maintenance, ...answer.maintenance } } : record
      );
    },
    onSettled: (_answer, _error, { id }) => {
      void client.invalidateQueries({ queryKey: serverScanKeys.servers });
      void client.invalidateQueries({ queryKey: serverScanKeys.sites });
      void client.invalidateQueries({ queryKey: serverScanKeys.server(id) });
    },
  });
}

/** A server's page (§9.4): its record, read on open and again after 30 seconds; never polled. */
export function useServerScanRecord(id: string) {
  return useQuery<ServerRecord>({
    queryKey: serverScanKeys.server(id),
    queryFn: () => serverScanApi.server(id),
    staleTime: RECORD_STALE_MS,
    retry: retryUnlessProblem,
    enabled: id.length > 0,
  });
}

/** The host a KubeVirt VM runs on, read with its record; only for a VM (`enabled`). */
export function useServerScanVmHost(id: string, enabled: boolean) {
  return useQuery<VmHostAnswer>({
    queryKey: serverScanKeys.vmHost(id),
    queryFn: () => serverScanApi.vmHost(id),
    staleTime: RECORD_STALE_MS,
    retry: retryUnlessProblem,
    enabled,
  });
}

/**
 * A server's History (§9.4), 50 events a page over server-scan's cursors,
 * newest first. `enabled` while the tab is shown and History works here (the
 * auditor token, §9.5), so nothing is asked otherwise.
 */
export function useServerScanHistory(id: string, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: serverScanKeys.history(id),
    queryFn: ({ pageParam }) => serverScanApi.history(id, pageParam),
    initialPageParam: "",
    getNextPageParam: (last: AuditEventPage) => (last.page.has_more ? (last.page.next_cursor ?? undefined) : undefined),
    staleTime: RECORD_STALE_MS,
    retry: retryUnlessProblem,
    enabled,
  });
}
