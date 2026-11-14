/**
 * The Events page's mocks (docs/notes/2026-11-13-server-scan-area-api.md §14),
 * typed so a shape change fails `tsc`: two pages of server-scan's audit trail
 * in its `GET /api/v1/events` shape (a job run by hand with no server, a
 * Wingman maintenance on a server, a pruned server; then a health change and
 * a discovery), and its actors, busiest first. The server is the server
 * page's fixture, so its link opens that page.
 */

import type { Page, Route } from "@playwright/test";
import { fulfillProblem, json } from "./api-handlers";
import { NODE, NODE_ID, setUpServer } from "./server-scan-server";
import type { EventActorList } from "../../types/server-scan-events";
import type { AuditEvent, AuditEventPage } from "../../types/server-scan-record";

export const PRUNED_ID = "srv_00000000000000000000000000000999";

const event = (id: string, event_type: string, created_at: string, over: Partial<AuditEvent> = {}): AuditEvent => ({
  id,
  event_type,
  server_id: NODE_ID,
  server_name: NODE,
  actor: { type: "SYSTEM", id: "ingestion", display: null },
  request_id: null,
  created_at,
  data: {},
  ...over,
});

/** Two pages, three events then two, newest first; the first carries the total. */
const EVENT_PAGES: AuditEventPage[] = [
  {
    items: [
      event("e5", "JOB_TRIGGERED", "2026-11-14T08:05:00Z", {
        server_id: null,
        server_name: null,
        actor: { type: "USER", id: "alice", display: "Alice Cohen" },
        data: { cronjob: "collector-openmanage-site1", job: "collector-openmanage-site1-manual-8kq2d" },
      }),
      event("e4", "MAINTENANCE_ENABLED", "2026-11-12T09:14:00Z", {
        actor: { type: "TOKEN", id: "api-token-admin", display: null },
        data: { reason: "Replacing PSU 2 — INC-4417" },
      }),
      event("e3", "SERVER_PRUNED", "2026-10-27T06:00:00Z", { server_id: PRUNED_ID, server_name: null }),
    ],
    page: { next_cursor: "c2", has_more: true, page_size: 3, total: 5 },
  },
  {
    items: [
      event("e2", "HEALTH_CHANGED", "2026-10-11T08:00:00Z", { data: { from: "HEALTHY", to: "WARNING", from_reasons: [], to_reasons: [] } }),
      event("e1", "SERVER_CREATED", "2026-09-01T06:00:00Z"),
    ],
    page: { next_cursor: null, has_more: false, page_size: 3, total: null },
  },
];

export const NO_EVENTS: AuditEventPage = { items: [], page: { next_cursor: null, has_more: false, page_size: 50, total: 0 } };

const ACTORS: EventActorList = {
  items: [
    { id: "ingestion", type: "SYSTEM", display: null, event_count: 9 },
    { id: "alice", type: "USER", display: "Alice Cohen", event_count: 3 },
    { id: "api-token-admin", type: "TOKEN", display: null, event_count: 2 },
  ],
};

export const AUDITOR_OFF =
  "Events needs server-scan's auditor token: add the key auditor-token to the server-scan Secret and restart day1 (SERVER_SCAN_AUDITOR_TOKEN).";

/** day1's answer without server-scan's auditor token: a `501` naming it in `details.setting`. */
export const auditorOff = (route: Route) =>
  fulfillProblem(route, 501, "FEATURE_DISABLED", AUDITOR_OFF, { setting: "SERVER_SCAN_AUDITOR_TOKEN" });

type Handler = (route: Route) => Promise<void> | void;

/** Every list read's query (`page_size` left out), in order. */
export interface EventCalls {
  lists: Record<string, string>[];
  actorReads: () => number;
}

/**
 * An admin, the area's reads and the server page's (so a server's link opens
 * it), then day1's two Events routes: the list by cursor ("" the first page,
 * "c2" the second), each read's query recorded, and the actors. A `Handler`
 * answers instead. Register a test's own routes after this.
 */
export async function setUpEvents(
  page: Page,
  { events = EVENT_PAGES, actors = ACTORS }: { events?: AuditEventPage[] | Handler; actors?: EventActorList | Handler } = {}
): Promise<EventCalls> {
  let actorReads = 0;
  const calls: EventCalls = { lists: [], actorReads: () => actorReads };
  await setUpServer(page);
  await page.route(/\/api\/day1\/server-scan\/events(\?.*)?$/, (route) => {
    const query = Object.fromEntries(new URL(route.request().url()).searchParams);
    const filters = { ...query };
    delete filters.page_size;
    calls.lists.push(filters);
    if (typeof events === "function") return events(route);
    return json(route, query.cursor === "c2" ? events[1] : events[0]);
  });
  await page.route(/\/api\/day1\/server-scan\/events\/actors$/, (route) => {
    actorReads += 1;
    return typeof actors === "function" ? actors(route) : json(route, actors);
  });
  return calls;
}
