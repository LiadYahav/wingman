/**
 * The Events page's filters (docs/notes/2026-11-13-server-scan-area-api.md
 * §14.1): read from the URL under server-scan's parameter names, turned into
 * the list's query, and the User filter's choices.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/features/events/filters.ts`, the URL
 * handling of `EventsPage.tsx` and the choices of `ActorCombobox.tsx`.
 */

import type { EventActor, EventListParams } from "@/types/server-scan-events";
import { actorLabel } from "./actor";
import { parseIsraelInput } from "./datetime";

export const RANGE_PRESETS = [
  { value: "1h", label: "Last hour", ms: 3_600_000 },
  { value: "24h", label: "Last 24 hours", ms: 86_400_000 },
  { value: "7d", label: "Last 7 days", ms: 7 * 86_400_000 },
  { value: "30d", label: "Last 30 days", ms: 30 * 86_400_000 },
] as const;

/** The custom range's value, after the presets. */
export const CUSTOM_RANGE = "custom";

/** How a custom bound is typed, in Israel's time. */
export const DATE_HINT = "DD/MM/YYYY HH:MM";

/** Event types renamed since a URL was bookmarked; "Health changes" was a shortcut value. */
const LEGACY_EVENT_TYPES: Record<string, string> = {
  HEALTH_STATUS_CHANGED: "HEALTH_CHANGED",
  "Health changes": "HEALTH_CHANGED",
};

export function normalizeEventType(value: string): string {
  return LEGACY_EVENT_TYPES[value] ?? value;
}

/** The page's filters as the URL holds them; "" is not set. */
export interface EventFilters {
  server: string;
  eventType: string;
  actorId: string;
  /** "" (any time), a preset's value, or `CUSTOM_RANGE`. */
  range: string;
  /** Custom bounds, `DD/MM/YYYY [HH:MM]` in Israel's time, as typed. */
  from: string;
  to: string;
}

/** Each filter's URL parameter: server-scan's names. */
const FILTER_PARAMS: Record<keyof EventFilters, string> = {
  server: "server_name",
  eventType: "event_type",
  actorId: "actor_id",
  range: "range",
  from: "from",
  to: "to",
};

/** The filters in `params` (the page's URL); a bookmarked legacy event type reads as its new name. */
export function readEventFilters(params: { get(name: string): string | null }): EventFilters {
  const get = (key: keyof EventFilters) => params.get(FILTER_PARAMS[key]) ?? "";
  return {
    server: get("server"),
    eventType: normalizeEventType(get("eventType")),
    actorId: get("actorId"),
    range: get("range"),
    from: get("from"),
    to: get("to"),
  };
}

/** The page's address after setting one filter (`""` removes it); the other parameters stay. */
export function withFilter(pathname: string, search: string, key: keyof EventFilters, value: string): string {
  const next = new URLSearchParams(search);
  if (value) next.set(FILTER_PARAMS[key], value);
  else next.delete(FILTER_PARAMS[key]);
  const query = next.toString();
  return query ? `${pathname}?${query}` : pathname;
}

/** A custom bound that is typed but is not a real date: marked, and not sent. */
export function isBadDate(text: string): boolean {
  return text.trim() !== "" && parseIsraelInput(text) === null;
}

/** The filters as the list's query; `now` only matters for a preset, rounded down to the minute. */
export function filtersToParams(f: EventFilters, now: Date = new Date()): EventListParams {
  const params: EventListParams = {};
  if (f.server.trim()) params.server_name = f.server.trim();
  if (f.eventType) params.event_type = f.eventType;
  if (f.actorId) params.actor_id = f.actorId;
  const preset = RANGE_PRESETS.find((p) => p.value === f.range);
  if (preset) {
    const minute = Math.floor(now.getTime() / 60_000) * 60_000;
    params.since = new Date(minute - preset.ms).toISOString();
  } else if (f.range === CUSTOM_RANGE) {
    const since = parseIsraelInput(f.from);
    const until = parseIsraelInput(f.to);
    if (since) params.since = since;
    if (until) params.until = until;
  }
  return params;
}

/** One choice of the User filter: what it filters by, and how it reads (a `ComboboxOption`). */
interface ActorChoice {
  value: string;
  label: string;
  /** Its event count, under the label. */
  description?: string;
}

/** The User filter's "All": it clears the filter. */
export const ALL_ACTORS = "__all__";

function events(count: number): string {
  return `${count.toLocaleString()} ${count === 1 ? "event" : "events"}`;
}

/** The User filter's choices: "All" first, then each actor as server-scan names it, with its count, busiest first. */
export function actorOptions(actors: readonly EventActor[]): ActorChoice[] {
  return [
    { value: ALL_ACTORS, label: "All" },
    ...actors.map((actor) => ({ value: actor.id, label: actorLabel(actor).label, description: events(actor.event_count) })),
  ];
}
