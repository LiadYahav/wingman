import { describe, expect, it } from "vitest";
import type { Breakdown, SiteStats, SiteStatsList } from "@/types/server-scan";
import { fleetHealth } from "./fleet-health";

const breakdown = (health: Breakdown["by_health"], in_maintenance = 0): Breakdown => ({
  total: Object.values(health).reduce((a, b) => a + (b ?? 0), 0), by_vendor: [], by_health: health, in_maintenance,
});

const site = (site_id: string, name: string, stats: Breakdown): SiteStats => ({
  site_id, name, ...stats, by_installation_type: {}, by_openshift_state: {},
});

const LIST: SiteStatsList = {
  items: [
    site("tlv", "Tel Aviv", breakdown({ HEALTHY: 20, WARNING: 1, CRITICAL: 2, UNKNOWN: 0 }, 1)),
    site("empty", "Empty", breakdown({})),
    site("unassigned", "Unassigned", breakdown({ UNKNOWN: 2 })),
  ],
  fleet: { ...breakdown({ HEALTHY: 20, WARNING: 1, CRITICAL: 2, UNKNOWN: 2 }, 1), by_installation_type: {}, by_openshift_state: {} },
};

describe("the fleet health", () => {
  it("counts each site's healthy first, then server-scan's counts above zero, each with its Servers filter", () => {
    const health = fleetHealth(LIST);
    const tlv = health.sites[0];
    expect(tlv.counts.map((c) => [c.kind, c.count, c.filter])).toEqual([
      ["healthy", 20, "site_id=tlv&health_overall=HEALTHY"],
      ["critical", 2, "site_id=tlv&health_overall=CRITICAL"],
      ["warning", 1, "site_id=tlv&health_overall=WARNING"],
      ["maintenance", 1, "site_id=tlv&maintenance=true"],
    ]);
    expect(tlv.parts).toEqual([
      { severity: "HEALTHY", count: 20 }, { severity: "WARNING", count: 1 }, { severity: "CRITICAL", count: 2 },
    ]);
    expect(tlv.filter).toBe("site_id=tlv");
  });

  it("keeps a configured site with no server, and Unassigned only when it holds one", () => {
    const health = fleetHealth(LIST);
    expect(health.sites.map((s) => [s.key, s.total, s.counts.length])).toEqual([["tlv", 23, 4], ["empty", 0, 0], ["unassigned", 2, 1]]);
    expect(health.siteCount).toBe(2);
    const without = fleetHealth({ ...LIST, items: LIST.items.map((s) => (s.site_id === "unassigned" ? { ...s, ...breakdown({}) } : s)) });
    expect(without.sites.map((s) => s.key)).toEqual(["tlv", "empty"]);
  });

  it("sums the fleet as server-scan does, its filters every site's", () => {
    const { fleet } = fleetHealth(LIST);
    expect(fleet.total).toBe(25);
    expect(fleet.counts.map((c) => [c.kind, c.filter])).toEqual([
      ["healthy", "health_overall=HEALTHY"],
      ["critical", "health_overall=CRITICAL"],
      ["warning", "health_overall=WARNING"],
      ["maintenance", "maintenance=true"],
      ["unknown", "health_overall=UNKNOWN"],
    ]);
  });
});
