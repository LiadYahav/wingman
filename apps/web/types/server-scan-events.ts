/**
 * The Events page's answers and query (docs/notes/2026-11-13-server-scan-area-api.md
 * §14.4): server-scan's own shapes, as day1 sends them. A page of events is
 * History's `AuditEventPage`. Ported from team-redbull/server-scan at 92146d3,
 * `frontend/src/types/events.ts` and `frontend/src/api/events.ts` (decision 18).
 */

import type { Actor } from "./server-scan-record";

/** One row of `GET /api/day1/server-scan/events/actors`: who wrote events, and how many. */
export interface EventActor extends Actor {
  event_count: number;
}

export interface EventActorList {
  /** Busiest first, at most 200. */
  items: EventActor[];
}

/** `GET /api/day1/server-scan/events`'s filters, under server-scan's names; a filter left out is not sent. */
export interface EventListParams {
  /** A case-insensitive part of the server's name. */
  server_name?: string;
  /** ISO 8601 in UTC, inclusive. */
  since?: string;
  /** ISO 8601 in UTC, exclusive. */
  until?: string;
  event_type?: string;
  /** An actor's exact id. */
  actor_id?: string;
}
