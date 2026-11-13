import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api-client";
import type { ErrorCode } from "@/types";
import type { InventoryRun, MceInventory } from "@/types/inventory";
import { bySite, hardwareLabel, totalAvailable } from "./pools";
import { originLabel, readablePhase, runSubject, runTone, runningCount } from "./runs";
import { MAX_SERVERS, addRequest, isSettled, refusalTitle, startSummary, toggled } from "./start";

const mce = (name: string, site: string, overrides: Partial<MceInventory> = {}): MceInventory => ({
  site, mce: name, known: true, servers: 3, in_clusters: 1, available: 2, usable: 2,
  pools: [], infra_envs: [], infra_envs_error: null, ...overrides,
});

const run = (overrides: Partial<InventoryRun> = {}): InventoryRun => ({
  workflow_id: "add-server-to-mce-ocp4-prod-mce-site1-a_pool_1", status: "running",
  started_at: null, closed_at: null, mce: "ocp4-prod-mce-site1-a", infra_env: "pool", slot: 1,
  server_name: null, origin: "pool", phase: null, error: null, ...overrides,
});

const problem = (status: number, code: ErrorCode) =>
  new ApiError(status, { type: "x", title: "x", status, detail: "d", instance: "/", code, request_id: null, details: {} }, "x");

describe("the pools", () => {
  it("are grouped by site, in day1's order, an MCE with nothing to show kept as a name", () => {
    const groups = bySite([
      mce("a", "site1"),
      mce("b", "site2"),
      mce("c", "site1", { known: false }),
      mce("d", "site1", { known: false, pools: [{ infra_env: "p", available: 0, usable: 0, hardware: [], drawable: 0 }] }),
    ]);
    expect(groups.map((g) => [g.site, g.mces.map((m) => m.mce), g.quiet.map((m) => m.mce)])).toEqual([
      ["site1", ["a", "d"], ["c"]],
      ["site2", ["b"], []],
    ]);
  });

  it("label hardware as server-scan gives it, and sum the available Agents", () => {
    expect(hardwareLabel({ vendor: "dell", model: "PowerEdge R650" })).toBe("dell PowerEdge R650");
    expect(hardwareLabel({ vendor: null, model: null })).toBe("Unknown hardware");
    expect(totalAvailable([mce("a", "s"), mce("b", "s", { available: 5 })])).toBe(7);
  });
});

describe("a run", () => {
  it("never guesses who started a pool draw", () => {
    expect(originLabel("named")).toBe("Person");
    expect(originLabel("pool")).toBe("herzi or a person");
    expect(originLabel(null)).toBe("Unknown");
  });

  it("shows its server once chosen, else its slot", () => {
    expect(runSubject(run())).toBe("slot 1");
    expect(runSubject(run({ server_name: "ocp-x" }))).toBe("ocp-x");
    expect(runSubject(run({ slot: null }))).toBe("—");
  });

  it("keeps the workflow's phase, only readable, and colours its status", () => {
    expect(readablePhase("waiting-for-agent")).toBe("waiting for agent");
    expect(readablePhase(null)).toBeNull();
    expect(readablePhase("completed", "completed")).toBeNull();
    expect(["RUNNING", "completed", "TIMED_OUT", "paused"].map(runTone)).toEqual(["running", "completed", "failed", "other"]);
    expect(runningCount([run(), run({ status: "failed" })])).toBe(1);
  });
});

describe("adding servers", () => {
  it("sends a count of 1 to 20, or 1 to 20 names, and nothing else", () => {
    expect(addRequest("count", 3, [])).toEqual({ count: 3 });
    expect(addRequest("count", 0, [])).toBeNull();
    expect(addRequest("count", MAX_SERVERS + 1, [])).toBeNull();
    expect(addRequest("count", 1.5, [])).toBeNull();
    expect(addRequest("named", 3, ["a"])).toEqual({ server_names: ["a"] });
    expect(addRequest("named", 3, [])).toBeNull();
  });

  it("picks names up to the limit", () => {
    expect(toggled(["a"], "b")).toEqual(["a", "b"]);
    expect(toggled(["a", "b"], "a")).toEqual(["b"]);
    const full = Array.from({ length: MAX_SERVERS }, (_, i) => `s${i}`);
    expect(toggled(full, "more")).toBe(full);
  });

  it("reads the per-run answer in one line", () => {
    expect(startSummary({ started: 2, already_running: 1, failed: 0, runs: [] })).toBe("2 started · 1 already running");
    expect(startSummary({ started: 0, already_running: 0, failed: 0, runs: [] })).toBe("Nothing started");
  });

  it("sends nothing more after an unanswered start, and says to look at the runs", () => {
    expect(isSettled(problem(504, "AMBIGUOUS_WRITE"))).toBe(true);
    expect(isSettled(problem(422, "VALIDATION_ERROR"))).toBe(false);
    expect(refusalTitle(problem(504, "AMBIGUOUS_WRITE"))).toMatch(/Look at the runs before sending again/);
    expect(refusalTitle(problem(502, "DEPENDENCY_UNAVAILABLE"))).toMatch(/^Nothing started/);
  });
});
