import { describe, expect, it } from "vitest";
import {
  countUpgrades,
  matchesUpgradeFilter,
  openByCluster,
  rowUpgrade,
  stateWord,
  upgradeFilterOf,
  withStartedRun,
  withUpgradeFilter,
} from "@/lib/fleet-upgrades";
import type { FleetUpgrade, UpgradeRun } from "@/types";

const LARK = "ocp4-prod-lark-site1";

const run = (overrides: Partial<FleetUpgrade> = {}): FleetUpgrade => ({
  workflow_id: `upgrade-cluster-${LARK}`,
  cluster: LARK,
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

const hawk = run({ workflow_id: "upgrade-cluster-ocp4-prod-hawk-site1", cluster: "ocp4-prod-hawk-site1", status: "completed", outcome: "cancelled", phase: null });

describe("the fleet's upgrade runs", () => {
  it("keeps only the clusters whose upgrade is open", () => {
    expect([...openByCluster([run(), hawk]).keys()]).toEqual([LARK]);
  });

  it("says the phase while open, paused when paused, and how it ended once closed", () => {
    expect(stateWord(run())).toBe("awaiting-approval");
    expect(stateWord(run({ paused: true, phase: "nodepool-roll" }))).toBe("paused");
    expect(stateWord(run({ phase: null }))).toBeNull();
    expect(stateWord(run({ status: "completed", outcome: "done", phase: null }))).toBe("done");
    expect(stateWord(run({ status: "failed", outcome: null, phase: null }))).toBe("failed");
  });
});

describe("a row's upgrade", () => {
  const open = openByCluster([run(), hawk]);

  it("is its open run, even when its MCE offers a newer release", () => {
    expect(rowUpgrade({ name: LARK, upgrade_available: "4.18.56" }, open)).toEqual({ kind: "upgrading", run: run() });
  });

  it("is the suggestion when it has no open run, a finished one included", () => {
    expect(rowUpgrade({ name: "ocp4-prod-hawk-site1", upgrade_available: "4.18.56" }, open)).toEqual({
      kind: "available",
      version: "4.18.56",
    });
  });

  it("is nothing when up to date, or while upgrades are off", () => {
    expect(rowUpgrade({ name: "ocp4-prod-owl-site1", upgrade_available: null }, open)).toBeNull();
    expect(rowUpgrade({ name: LARK, upgrade_available: null }, new Map())).toBeNull();
  });

  it("is counted and filtered by its kind", () => {
    const rows = [
      rowUpgrade({ name: LARK, upgrade_available: "4.18.56" }, open),
      rowUpgrade({ name: "a", upgrade_available: "4.18.56" }, open),
      rowUpgrade({ name: "b", upgrade_available: "4.21.40" }, open),
      rowUpgrade({ name: "c", upgrade_available: null }, open),
    ];
    expect(countUpgrades(rows)).toEqual({ available: 2, upgrading: 1 });
    expect(rows.map((r) => matchesUpgradeFilter(r, "available"))).toEqual([false, true, true, false]);
    expect(rows.map((r) => matchesUpgradeFilter(r, "upgrading"))).toEqual([true, false, false, false]);
    expect(rows.every((r) => matchesUpgradeFilter(r, "all"))).toBe(true);
  });
});

describe("the Upgrades filter in the URL", () => {
  it("reads ?upgrade=, anything else is All", () => {
    expect(upgradeFilterOf("?upgrade=available")).toBe("available");
    expect(upgradeFilterOf("?site=x&upgrade=upgrading")).toBe("upgrading");
    expect(upgradeFilterOf("")).toBe("all");
    expect(upgradeFilterOf("?upgrade=everything")).toBe("all");
  });

  it("writes it, keeping the rest of the URL, and All leaves no trace", () => {
    const at = (search: string, hash = "") => ({ pathname: "/clusters", search, hash });
    expect(withUpgradeFilter(at(""), "upgrading")).toBe("/clusters?upgrade=upgrading");
    expect(withUpgradeFilter(at("?x=1", "#top"), "available")).toBe("/clusters?x=1&upgrade=available#top");
    expect(withUpgradeFilter(at("?upgrade=available&x=1"), "all")).toBe("/clusters?x=1");
    expect(withUpgradeFilter(at("?upgrade=available"), "all")).toBe("/clusters");
  });
});

describe("after a start", () => {
  const started = {
    workflow_id: "upgrade-cluster-ocp4-prod-hawk-site1",
    cluster: "ocp4-prod-hawk-site1",
    status: "running",
    phase: null,
    waiting_for: null,
    mce: null,
    paused: false,
    outcome: null,
  } as UpgradeRun;

  it("the started run replaces the cluster's previous one, where day1 has the file kept", () => {
    const runs = withStartedRun([run(), hawk], started, "2026-11-13T11:00:00.000Z");
    expect(runs.map((r) => [r.cluster, r.status])).toEqual([
      ["ocp4-prod-hawk-site1", "running"],
      [LARK, "running"],
    ]);
    expect(runs[0]).toMatchObject({ site: "site1", mce: "ocp4-prod-mce-site1-a", started_at: "2026-11-13T11:00:00.000Z", outcome: null });
    expect(openByCluster(runs).has("ocp4-prod-hawk-site1")).toBe(true);
  });

  it("a cluster's first run is added", () => {
    expect(withStartedRun([], started, "t")).toHaveLength(1);
  });
});
