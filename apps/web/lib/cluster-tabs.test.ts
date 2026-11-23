import { describe, expect, it } from "vitest";
import { CLUSTER_TABS, offersNodesTab, requestedTab, shownTab } from "@/lib/cluster-tabs";

describe("the cluster page's tabs", () => {
  it("opens the tab ?tab= names, and Overview for anything else", () => {
    for (const tab of CLUSTER_TABS) expect(requestedTab(tab)).toBe(tab);
    expect(requestedTab(null)).toBe("overview");
    expect(requestedTab("servers")).toBe("overview");
    expect(requestedTab("")).toBe("overview");
  });

  it("offers the Nodes tab to an admin, and to nobody known to be a viewer", () => {
    expect(offersNodesTab({ mounted: true, isAdmin: true })).toBe(true);
    expect(offersNodesTab({ mounted: true, isAdmin: false })).toBe(false);
  });

  it("keeps the Nodes tab until the role is known, so an admin's never flickers away", () => {
    // Before mount the persisted store is not read yet: every visitor looks like a viewer
    expect(offersNodesTab({ mounted: false, isAdmin: false })).toBe(true);
    expect(offersNodesTab({ mounted: false, isAdmin: true })).toBe(true);
  });

  it("shows Overview for a viewer's ?tab=nodes, and every other tab as asked", () => {
    expect(shownTab("nodes", false)).toBe("overview");
    expect(shownTab("nodes", true)).toBe("nodes");
    for (const tab of CLUSTER_TABS.filter((t) => t !== "nodes")) {
      expect(shownTab(tab, false)).toBe(tab);
      expect(shownTab(tab, true)).toBe(tab);
    }
  });
});
