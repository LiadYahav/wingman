import { describe, expect, it } from "vitest";
import { segmentsSidebar } from "./sidebar";
import { DEFAULT_VIEW, type SegmentsView } from "./view";

const STATS = [
  { site: "site1", total_segments: 12, allocated: 10, by_type: [] },
  { site: "site3", total_segments: 0, allocated: 0, by_type: [] },
];

const view = (overrides: Partial<SegmentsView>): SegmentsView => ({ ...DEFAULT_VIEW, ...overrides });
const section = (v: SegmentsView, label: string, sites: Parameters<typeof segmentsSidebar>[1] = { sites: STATS }) =>
  segmentsSidebar(v, sites).find((s) => s.label === label)!;
const active = (v: SegmentsView, label: string) =>
  section(v, label).items.filter((i) => i.active).map((i) => i.key);

describe("the Segments sidebar", () => {
  it("has the page's options in three sections", () => {
    expect(segmentsSidebar(DEFAULT_VIEW, { sites: STATS }).map((s) => [s.label, s.items.map((i) => i.label)])).toEqual([
      ["Segments", ["All", "Available", "Allocated", "Disagrees with Git"]],
      ["Sites", ["site1", "site3"]],
      ["Help", ["Documentation"]],
    ]);
  });

  it("marks the status preset the URL has, and Disagrees with Git on its own", () => {
    expect(active(DEFAULT_VIEW, "Segments")).toEqual(["all"]);
    expect(active(view({ status: "allocated" }), "Segments")).toEqual(["allocated"]);
    expect(active(view({ mismatch: true }), "Segments")).toEqual(["mismatch"]);
    expect(active(view({ status: "available", mismatch: true }), "Segments")).toEqual([]);
  });

  it("sets only its own filters, keeping the rest of the view", () => {
    const busy = view({ site: "site1", q: "herzi", sort: { id: "vlan_id", desc: true }, mismatch: true });
    const hrefs = Object.fromEntries(section(busy, "Segments").items.map((i) => [i.key, i.href]));
    expect(hrefs.allocated).toBe("/segments?status=allocated&site=site1&q=herzi&sort=-vlan_id");
    expect(hrefs.all).toBe("/segments?site=site1&q=herzi&sort=-vlan_id");
    expect(hrefs.mismatch).toBe("/segments?site=site1&q=herzi&mismatch=1&sort=-vlan_id");
  });

  it("lists every site with used out of total, an empty one too; the active one's link clears it", () => {
    const sites = section(view({ site: "SITE1", status: "available" }), "Sites").items;
    expect(sites.map((s) => [s.label, s.meta, s.active])).toEqual([
      ["site1", "10/12", true],
      ["site3", "0/0", false],
    ]);
    expect(sites[0].href).toBe("/segments?status=available");
    expect(sites[1].href).toBe("/segments?status=available&site=site3");
    expect(sites[0].metaLabel).toBe("10 of 12 segments allocated");
  });

  it("says when the sites are loading or could not be read", () => {
    expect(section(DEFAULT_VIEW, "Sites", "loading")).toEqual({ label: "Sites", items: [], note: "Loading…" });
    expect(section(DEFAULT_VIEW, "Sites", "error").note).toBe("The sites could not be read.");
  });

  it("links Documentation to Wingman's docs page", () => {
    expect(section(DEFAULT_VIEW, "Help").items).toEqual([
      { key: "docs", label: "Documentation", icon: "docs", href: "/docs", active: false },
    ]);
  });
});
