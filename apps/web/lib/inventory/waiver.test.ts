import { describe, expect, it } from "vitest";
import type { Candidate } from "@/types/inventory";
import { groupCandidates, needsFixChosen, totalSum, withWaiver } from "./waiver";

const candidate = (name: string, overrides: Partial<Candidate> = {}): Candidate => ({
  id: `srv_${name}`, name, vendor: "dell", model: "PowerEdge R650", health: "HEALTHY", lock: null,
  offered: true, why_not: null, ready: true, health_problems: [], ...overrides,
});
const sick = (name: string) => candidate(name, { health: "CRITICAL", ready: false, health_problems: ["health CRITICAL"] });
const locked = (name: string) => candidate(name, { offered: false, ready: false, why_not: "locked by add-server-to-mce" });

describe("a pool's servers", () => {
  it("are listed ready, then needing a fix, then not offered, keeping day1's order and leaving empty groups out", () => {
    const groups = groupCandidates([locked("l"), candidate("a"), sick("s"), candidate("b")]);
    expect(groups.map((g) => [g.group.label, g.candidates.map((c) => c.name)])).toEqual([
      ["Ready", ["a", "b"]],
      ["Needs fix", ["s"]],
      ["Not offered", ["l"]],
    ]);
    expect(groupCandidates([candidate("a")]).map((g) => g.group.group)).toEqual(["ready"]);
    expect(groupCandidates([])).toEqual([]);
  });

  it("a locked server that is also unhealthy is not offered, never 'needs a fix'", () => {
    const both = candidate("x", { offered: false, ready: false, why_not: "in maintenance", health_problems: ["health CRITICAL"] });
    expect(groupCandidates([both]).map((g) => g.group.group)).toEqual(["not-offered"]);
    expect(needsFixChosen(["x"], [both])).toEqual([]);
  });
});

describe("the health waiver", () => {
  it("is asked for exactly the chosen servers that need a fix, in the order chosen", () => {
    const list = [candidate("a"), sick("s1"), sick("s2"), locked("l")];
    expect(needsFixChosen(["s2", "a", "s1", "gone"], list).map((c) => c.name)).toEqual(["s2", "s1"]);
    expect(needsFixChosen(["a"], list)).toEqual([]);
    expect(needsFixChosen(["s1"], undefined)).toEqual([]);
  });

  it("is only ever added to a named install, never to a pool draw", () => {
    expect(withWaiver({ server_names: ["s1"] })).toEqual({ server_names: ["s1"], allow_unhealthy: true });
    expect(withWaiver({ count: 2 })).toEqual({ count: 2 });
    expect("allow_unhealthy" in withWaiver({ count: 2 })).toBe(false);
  });
});

describe("a total", () => {
  it("says the sum behind it", () => {
    expect(totalSum({ available: 2, ready: 1, needs_fix: 1 })).toBe("2 available + 1 ready + 1 needs a fix");
    expect(totalSum({ available: 4, ready: null, needs_fix: null })).toBe("4 available + 0 ready + 0 need a fix");
  });
});
