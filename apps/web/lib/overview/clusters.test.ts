import { describe, expect, it } from "vitest";
import type { FleetUpgrade } from "@/types";
import { clustersBySite, percent, upgradeSummary, versionSpread } from "./clusters";

const at = (site: string, mce: string) => ({ site, mce });
const tagged = (mastertag: string | null) => ({ mastertag });
const cluster = (name: string, upgrade_available: string | null = null) => ({ name, upgrade_available });

const run = (cluster: string, status = "running"): FleetUpgrade => ({
  workflow_id: `upgrade-cluster-${cluster}`, cluster, site: "site1", mce: "m", status,
  started_at: null, closed_at: null, phase: null, waiting_for: null, paused: false, outcome: null,
});

describe("a share", () => {
  it("is a rounded percent, a count above zero never drawn as nothing", () => {
    expect(percent(1, 4)).toBe(25);
    expect(percent(1, 1000)).toBe(2);
    expect(percent(0, 10)).toBe(0);
    expect(percent(3, 0)).toBe(0);
    expect(percent(5, 4)).toBe(100);
  });
});

describe("the clusters by site", () => {
  it("count each site and its MCEs, the most first, a tie by name", () => {
    const sites = clustersBySite([
      at("site2", "mce-b"), at("site1", "mce-a"), at("site1", "mce-a"), at("site2", "mce-c"), at("site1", "mce-z"), at("site10", "mce-x"),
    ]);
    expect(sites).toEqual([
      { site: "site1", count: 3, mces: [{ mce: "mce-a", count: 2 }, { mce: "mce-z", count: 1 }] },
      { site: "site2", count: 2, mces: [{ mce: "mce-b", count: 1 }, { mce: "mce-c", count: 1 }] },
      { site: "site10", count: 1, mces: [{ mce: "mce-x", count: 1 }] },
    ]);
  });

  it("are none without clusters", () => {
    expect(clustersBySite([])).toEqual([]);
  });
});

describe("the version spread", () => {
  it("counts each mastertag, newest first by number, files without one last", () => {
    const spread = versionSpread([
      tagged("4.16.9-x86_64"), tagged("4.16.27-x86_64"), tagged(null), tagged("4.16.27-x86_64"), tagged("4.14.3-x86_64"), tagged(" "),
    ]);
    expect(spread).toEqual({
      rows: [
        { version: "4.16.27-x86_64", count: 2 },
        { version: "4.16.9-x86_64", count: 1 },
        { version: "4.14.3-x86_64", count: 1 },
        { version: null, count: 2 },
      ],
      rest: null,
    });
  });

  it("sums what does not fit", () => {
    const spread = versionSpread([tagged("4.17.1"), tagged("4.16.1"), tagged("4.15.1"), tagged("4.15.1"), tagged("4.14.1")], 2);
    expect(spread.rows.map((r) => r.version)).toEqual(["4.17.1", "4.16.1"]);
    expect(spread.rest).toEqual({ versions: 2, clusters: 3 });
  });
});

describe("the upgrade counts", () => {
  it("count the clusters list's filters: an open run wins over an available release", () => {
    const clusters = [cluster("a", "4.17.2"), cluster("b", "4.17.2"), cluster("c"), cluster("d")];
    expect(upgradeSummary(clusters, [run("a"), run("c"), run("d", "completed")], { failed: false })).toEqual({
      on: true, available: 1, upgrading: 2,
    });
  });

  it("say nothing while upgrades are off", () => {
    expect(upgradeSummary([cluster("a"), cluster("b")], null, { failed: false })).toEqual({ on: false });
  });

  it("know no running count when the runs could not be read, never zero", () => {
    expect(upgradeSummary([cluster("a", "4.17.2")], null, { failed: true })).toEqual({ on: true, available: 1, upgrading: null });
    expect(upgradeSummary([cluster("a")], null, { failed: true })).toEqual({ on: true, available: 0, upgrading: null });
  });
});
