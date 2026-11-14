/**
 * day1's Events page routes (docs/notes/2026-11-13-server-scan-area-api.md
 * §14, ADR-0048's 3.31.0 amendment): server-scan's audit trail of the fleet,
 * filtered and in cursor pages, and who wrote it. Admins only, as the area;
 * read with server-scan's auditor token, as History: without it both answer
 * `501` with `details.setting` naming it.
 */

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { retryUnlessProblem } from "@/lib/api/server-scan";
import type { EventActorList, EventListParams } from "@/types/server-scan-events";
import type { AuditEventPage } from "@/types/server-scan-record";

/** As server-scan's page: 50 events a page, newest first. */
const EVENTS_PAGE_SIZE = 50;
/** As server-scan's query client: the list is read on open, and again when opened after 30 seconds (§14.1). */
const EVENTS_STALE_MS = 30_000;
/** As server-scan's User list: read again after a minute; it changes only when someone first acts. */
const ACTORS_STALE_MS = 60_000;
const EVENTS_PATH = "/api/day1/server-scan/events";

function eventsPage(params: EventListParams, cursor: string) {
  const query = new URLSearchParams({ ...params, page_size: String(EVENTS_PAGE_SIZE) });
  if (cursor) query.set("cursor", cursor);
  return api.get<AuditEventPage>(`${EVENTS_PATH}?${query}`);
}

/** One filter's pages of the trail over server-scan's cursors; a change of filters is a new list. */
export function useServerScanEvents(params: EventListParams) {
  return useInfiniteQuery({
    queryKey: ["server-scan", "events", params],
    queryFn: ({ pageParam }) => eventsPage(params, pageParam),
    initialPageParam: "",
    getNextPageParam: (last: AuditEventPage) => (last.page.has_more ? (last.page.next_cursor ?? undefined) : undefined),
    staleTime: EVENTS_STALE_MS,
    retry: retryUnlessProblem,
  });
}

/** Who wrote the trail, busiest first: the User filter's choices. */
export function useServerScanEventActors() {
  return useQuery<EventActorList>({
    queryKey: ["server-scan", "event-actors"],
    queryFn: () => api.get<EventActorList>(`${EVENTS_PATH}/actors`),
    staleTime: ACTORS_STALE_MS,
    retry: retryUnlessProblem,
  });
}
