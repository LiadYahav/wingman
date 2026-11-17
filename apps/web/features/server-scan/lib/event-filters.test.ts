/**
 * The Events page's filters: server-scan's `features/events/filters.test.ts`
 * cases and the User list's from `EventsUi.test.tsx` at 92146d3 (decision 18),
 * plus the URL Wingman keeps them in.
 */

import { describe, expect, it } from "vitest";
import {
  ALL_ACTORS, actorOptions, filtersToParams, isBadDate, normalizeEventType, readEventFilters, withFilter, type EventFilters,
} from "./event-filters";

const BASE: EventFilters = { server: "", eventType: "", actorId: "", range: "", from: "", to: "" };

describe("filtersToParams", () => {
  it("maps server, type and user to their API params", () => {
    expect(filtersToParams({ ...BASE, server: " ocp-dell ", eventType: "SERVER_PRUNED", actorId: "alice" })).toEqual({
      server_name: "ocp-dell",
      event_type: "SERVER_PRUNED",
      actor_id: "alice",
    });
  });

  it("sends nothing for empty filters", () => {
    expect(filtersToParams(BASE)).toEqual({});
    expect(filtersToParams({ ...BASE, server: "   " })).toEqual({});
  });

  it("turns a preset into since, relative to now, rounded down to the minute", () => {
    const now = new Date("2026-10-01T12:00:30Z");
    expect(filtersToParams({ ...BASE, range: "24h" }, now).since).toBe("2026-09-30T12:00:00.000Z");
    expect(filtersToParams({ ...BASE, range: "1h" }, now)).toEqual({ since: "2026-10-01T11:00:00.000Z" });
  });

  it("reads custom bounds as Israel time and sends UTC", () => {
    expect(filtersToParams({ ...BASE, range: "custom", from: "01/10/2026 09:00", to: "02/10/2026" })).toEqual({
      since: "2026-10-01T06:00:00.000Z",
      until: "2026-10-01T21:00:00.000Z",
    });
  });

  it("ignores an unparseable custom bound, and custom bounds without Custom", () => {
    expect(filtersToParams({ ...BASE, range: "custom", from: "garbage", to: "31/02/2026" })).toEqual({});
    expect(filtersToParams({ ...BASE, from: "01/10/2026 09:00" })).toEqual({});
  });
});

describe("normalizeEventType", () => {
  it("maps the old name and the old shortcut label to HEALTH_CHANGED", () => {
    expect(normalizeEventType("HEALTH_STATUS_CHANGED")).toBe("HEALTH_CHANGED");
    expect(normalizeEventType("Health changes")).toBe("HEALTH_CHANGED");
    expect(normalizeEventType("SERVER_CREATED")).toBe("SERVER_CREATED");
  });
});

describe("the filters in the URL", () => {
  it("are read under server-scan's names, a legacy type read as its new name", () => {
    const url = new URLSearchParams("event_type=HEALTH_STATUS_CHANGED&server_name=ocp-dell&actor_id=sys&range=custom&from=01/10/2026 09:00&to=02/10/2026");
    expect(readEventFilters(url)).toEqual({
      server: "ocp-dell", eventType: "HEALTH_CHANGED", actorId: "sys", range: "custom", from: "01/10/2026 09:00", to: "02/10/2026",
    });
    expect(readEventFilters(new URLSearchParams())).toEqual(BASE);
  });

  it("change one at a time, the others kept; an empty value removes it", () => {
    expect(withFilter("/server-scan/events", "", "eventType", "SERVER_PRUNED")).toBe("/server-scan/events?event_type=SERVER_PRUNED");
    expect(withFilter("/server-scan/events", "?event_type=SERVER_PRUNED&actor_id=alice", "actorId", "")).toBe("/server-scan/events?event_type=SERVER_PRUNED");
    expect(withFilter("/server-scan/events", "?actor_id=alice", "actorId", "")).toBe("/server-scan/events");
    expect(withFilter("/server-scan/events", "?range=custom", "from", "01/10/2026 09:00")).toBe("/server-scan/events?range=custom&from=01%2F10%2F2026+09%3A00");
  });

  it("mark a custom bound that is typed but is not a date", () => {
    expect(isBadDate("")).toBe(false);
    expect(isBadDate("01/10/2026")).toBe(false);
    expect(isBadDate("31/02/2026")).toBe(true);
    expect(isBadDate("tomorrow")).toBe(true);
  });
});

describe("the User filter's choices", () => {
  const ACTORS = [
    { id: "alice", type: "USER" as const, display: "Alice A", event_count: 3 },
    { id: "api-token-admin", type: "TOKEN" as const, display: null, event_count: 2 },
    { id: "api-token-viewer", type: "TOKEN" as const, display: null, event_count: 1 },
    { id: "ingest", type: "SYSTEM" as const, display: null, event_count: 9 },
  ];

  it("lists All first, then the actors in server-scan's order with their labels and counts", () => {
    expect(actorOptions(ACTORS).map((o) => [o.label, o.description ?? null])).toEqual([
      ["All", null],
      ["Alice A", "3 events"],
      ["API token (admin)", "2 events"],
      ["API token (viewer)", "1 event"],
      ["System (ingest)", "9 events"],
    ]);
  });

  it("chooses an actor by its id, and All clears", () => {
    expect(actorOptions(ACTORS).map((o) => o.value)).toEqual([ALL_ACTORS, "alice", "api-token-admin", "api-token-viewer", "ingest"]);
    expect(actorOptions([])).toEqual([{ value: ALL_ACTORS, label: "All" }]);
  });
});
