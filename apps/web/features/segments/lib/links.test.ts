import { describe, expect, it } from "vitest";
import { clusterSegmentsHref, clusterSegmentsLink } from "./links";
import { siteCard, updatedAgo } from "./sites";

const EXTERNAL = {
  url: "https://segments-manager.example/",
  search_url: "https://segments-manager.example/api/segments/search?q=ocp4-prod-herzi-site1",
};

describe("the links into segments", () => {
  it("opens Wingman's page filtered to the cluster", () => {
    expect(clusterSegmentsHref("ocp4-prod-herzi-site1")).toBe("/segments?cluster=ocp4-prod-herzi-site1");
    expect(clusterSegmentsHref("a&b")).toBe("/segments?cluster=a%26b");
  });

  it("is Wingman's page for someone with the area, segments-manager's for anyone else", () => {
    expect(clusterSegmentsLink("ocp4-prod-herzi-site1", { area: true, external: EXTERNAL })).toEqual({
      kind: "native",
      href: "/segments?cluster=ocp4-prod-herzi-site1",
    });
    expect(clusterSegmentsLink("ocp4-prod-herzi-site1", { area: false, external: EXTERNAL })).toEqual({
      kind: "external",
      url: EXTERNAL.url,
      searchUrl: EXTERNAL.search_url,
    });
  });

  it("is nothing without segments-manager, or while the area is still unknown", () => {
    expect(clusterSegmentsLink("x", { area: true, external: null })).toBeNull();
    expect(clusterSegmentsLink("x", { area: undefined, external: EXTERNAL })).toBeNull();
  });
});

describe("a site card", () => {
  it("is allocated out of total, with the types above zero in order", () => {
    expect(
      siteCard({
        site: "site1",
        total_segments: 12,
        allocated: 10,
        by_type: [
          { type: "HC", allocated: 6 },
          { type: "MCE", allocated: 0 },
          { type: "UPI", allocated: 4 },
        ],
      })
    ).toEqual({ site: "site1", allocated: 10, total: 12, full: false, types: [{ type: "HC", count: 6 }, { type: "UPI", count: 4 }] });
  });

  it("is full only when every segment is allocated, never for an empty site", () => {
    expect(siteCard({ site: "s", total_segments: 2, allocated: 2, by_type: [] }).full).toBe(true);
    expect(siteCard({ site: "s", total_segments: 0, allocated: 0, by_type: [] }).full).toBe(false);
  });
});

describe("updated ago", () => {
  it("says it in seconds, minutes or hours", () => {
    const now = 1_000_000_000;
    expect(updatedAgo(now - 2_000, now)).toBe("just now");
    expect(updatedAgo(now - 12_400, now)).toBe("12 s ago");
    expect(updatedAgo(now - 3 * 60_000, now)).toBe("3 min ago");
    expect(updatedAgo(now - 2 * 3_600_000, now)).toBe("2 h ago");
    expect(updatedAgo(now + 5_000, now)).toBe("just now");
  });
});
