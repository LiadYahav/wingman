import { describe, expect, it } from "vitest";
import { brief, clustersViewOf, fleetTone, openByCluster, stateWord, upgradeHref } from "@/lib/fleet-upgrades";
import type { FleetUpgrade } from "@/types";

const run = (overrides: Partial<FleetUpgrade> = {}): FleetUpgrade => ({
  workflow_id: "upgrade-cluster-ocp4-prod-lark-site1",
  cluster: "ocp4-prod-lark-site1",
  site: "site1",
  mce: "ocp4-prod-mce-site1-a",
  status: "running",
  started_at: "2026-11-13T10:00:00+00:00",
  closed_at: null,
  phase: "awaiting-approval",
  waiting_for: "approve: 4.18.22 → 4.18.56",
  paused: false,
  outcome: null,
  ...overrides,
});

describe("the fleet's upgrade runs", () => {
  it("badges only the clusters whose upgrade is open", () => {
    const hawk = run({ cluster: "ocp4-prod-hawk-site1", status: "completed", outcome: "cancelled", phase: null });
    expect([...openByCluster([run(), hawk]).keys()]).toEqual(["ocp4-prod-lark-site1"]);
  });

  it("says the phase while open, paused when paused, and how it ended once closed", () => {
    expect(stateWord(run())).toBe("awaiting-approval");
    expect(stateWord(run({ paused: true, phase: "nodepool-roll" }))).toBe("paused");
    expect(stateWord(run({ phase: null }))).toBeNull();
    expect(stateWord(run({ status: "completed", outcome: "done", phase: null }))).toBe("done");
    expect(stateWord(run({ status: "failed", outcome: null, phase: null }))).toBe("failed");
  });

  it("colours open, done, stopped by a person, and anything else as failed", () => {
    expect(fleetTone(run())).toBe("open");
    expect(fleetTone(run({ status: "completed", outcome: "done" }))).toBe("done");
    expect(fleetTone(run({ status: "completed", outcome: "aborted" }))).toBe("stopped");
    expect(fleetTone(run({ status: "terminated" }))).toBe("failed");
  });

  it("shortens waiting_for at a word and keeps a short one whole", () => {
    expect(brief("approve: 4.18.22 → 4.18.56")).toBe("approve: 4.18.22 → 4.18.56");
    const long = "continue, once the customer's readiness checks after the last step pass: prod-lark-site1-dell rolls next";
    const short = brief(long, 40);
    expect(short.length).toBeLessThanOrEqual(40);
    expect(short.endsWith("…")).toBe(true);
    expect(long.startsWith(short.slice(0, -1))).toBe(true);
    expect(brief("a\n  b")).toBe("a b");
  });

  it("links to the cluster's page, pinned to its file when day1 has one", () => {
    expect(upgradeHref(run())).toBe("/clusters/ocp4-prod-lark-site1?site=site1&mce=ocp4-prod-mce-site1-a");
    expect(upgradeHref(run({ site: null, mce: null }))).toBe("/clusters/ocp4-prod-lark-site1");
  });

  it("reads the view from the URL's hash", () => {
    expect(clustersViewOf("#upgrades")).toBe("upgrades");
    expect(clustersViewOf("")).toBe("clusters");
    expect(clustersViewOf("#other")).toBe("clusters");
  });
});
