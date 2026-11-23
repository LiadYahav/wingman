import { describe, expect, it } from "vitest";
import type { HerziMarks } from "@/types/inventory";
import { herziNote } from "./herzi";
import { usedHint } from "./used";

const NONE: HerziMarks = { ignored: false, paused: false, blocked_until: null, no_hardware_since: null };
const NOW = new Date("2026-11-23T10:00:00Z");

describe("herzi's marks on a pool", () => {
  it("say nothing when herzi marked nothing, or only a deadline that passed", () => {
    expect(herziNote(NONE, NOW)).toBeNull();
    expect(herziNote({ ...NONE, blocked_until: "2026-11-23T09:59:00+00:00" }, NOW)).toBeNull();
  });

  it("badge the first mark that applies and say every one in the tooltip", () => {
    const note = herziNote({ ...NONE, paused: true, no_hardware_since: "2026-11-23T09:00:00+00:00" }, NOW);
    expect(note?.label).toBe("herzi paused");
    expect(note?.hint).toContain('herzi.redbull.io/paused is "true"');
    expect(note?.hint).toContain("removes none of its used Agents");
    expect(note?.hint).toContain("found no hardware");
    expect(herziNote({ ...NONE, ignored: true, paused: true }, NOW)?.label).toBe("herzi ignores");
  });

  it("call a block marker still ahead an order in flight", () => {
    const note = herziNote({ ...NONE, blocked_until: "2026-11-23T10:05:00+00:00" }, NOW);
    expect(note?.label).toBe("herzi ordering");
    expect(note?.hint).toContain("herzi.redbull.io/blocked-until");
  });

  it("make a paused pool's used Agents wait in the used hint too", () => {
    const labels = { keys: ["redbull.io/ever-installed"], source: "herzi" as const };
    expect(usedHint(labels, ["s1"], true)).toContain("herzi is paused on this pool, so it removes none of them");
    expect(usedHint(labels, ["s1"])).not.toContain("paused");
  });
});
