/** server-scan's `frontend/src/lib/datetime.test.ts` cases at 92146d3 (decision 18). */

import { describe, expect, it } from "vitest";
import { formatAge, formatRelative, formatTimestamp } from "./datetime";

describe("an instant, in Israel's time", () => {
  it("is shown in Israel's zone whatever the stored UTC (winter, UTC+2)", () => {
    expect(formatTimestamp("2026-01-15T10:00:00Z")).toContain("12:00:00");
  });

  it("is day/month/year with a 24-hour clock", () => {
    expect(formatTimestamp("2026-09-30T21:34:17Z")).toMatch(/^01\/10\/2026, 00:34:17/);
    expect(formatTimestamp("2026-07-15T13:05:00Z")).toMatch(/^15\/07\/2026, 16:05:00/);
  });

  it("carries the summer offset too (IDT, UTC+3)", () => {
    expect(formatTimestamp("2026-07-15T10:00:00Z")).toContain("13:00:00");
  });
});

describe("a relative time", () => {
  const now = new Date("2026-09-13T12:00:00Z");
  it("coarsens with distance", () => {
    expect(formatRelative("2026-09-13T11:59:30Z", now)).toBe("30 seconds ago");
    expect(formatRelative("2026-09-13T11:15:00Z", now)).toBe("45 minutes ago");
    expect(formatRelative("2026-09-12T22:00:00Z", now)).toBe("14 hours ago");
    expect(formatRelative("2026-09-10T12:00:00Z", now)).toBe("3 days ago");
  });
});

describe("an age, as server-scan's Stale chip shows it", () => {
  const now = new Date("2026-11-13T12:00:00Z");
  it("is minutes under an hour, hours under a day, then days; never negative", () => {
    expect(formatAge("2026-11-13T11:15:00Z", now)).toBe("45m");
    expect(formatAge("2026-11-12T16:00:00Z", now)).toBe("20h");
    expect(formatAge("2026-11-10T12:00:00Z", now)).toBe("3d");
    expect(formatAge("2026-11-13T13:00:00Z", now)).toBe("0m");
  });
});
