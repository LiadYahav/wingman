import { describe, expect, it } from "vitest";
import { formatAge } from "./format";

describe("an age, as server-scan's Stale chip shows it", () => {
  const now = new Date("2026-11-13T12:00:00Z");
  it("is minutes under an hour, hours under a day, then days; never negative", () => {
    expect(formatAge("2026-11-13T11:15:00Z", now)).toBe("45m");
    expect(formatAge("2026-11-12T16:00:00Z", now)).toBe("20h");
    expect(formatAge("2026-11-10T12:00:00Z", now)).toBe("3d");
    expect(formatAge("2026-11-13T13:00:00Z", now)).toBe("0m");
  });
});
