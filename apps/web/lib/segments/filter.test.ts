import { describe, expect, it } from "vitest";
import { compareSegments, filterSegments, matchesSearch, shownSegments, sortSegments, statusCounts } from "./filter";
import { free, segment } from "./testing";
import { DEFAULT_VIEW, type SegmentsView } from "./view";

const HERZI = segment({ segment: "10.20.44.0/24", vlan_id: 1418, epg_name: "EPG_site1_HC_1418", cluster_name: "ocp4-prod-herzi-site1" });
const UPI = segment({
  segment: "10.20.60.0/24",
  vlan_id: 1460,
  epg_name: "EPG_site1_UPI_1460",
  type: "UPI",
  dhcp: false,
  cluster_name: ["ocp4-upi-a", "ocp4-upi-b"],
});
const FREE_2 = free({ segment: "10.20.52.0/24", site: "site2", vlan_id: 2452, epg_name: "EPG_site2_HC_2452" });
const MCE = segment({ segment: "10.20.70.0/24", vlan_id: 9, epg_name: "EPG_site2_MCE_9", site: "Site2", type: "MCE", cluster_name: "ocp4-prod-mce-site2-a" });
const OLD = segment({ segment: "10.20.80.0/24", vlan_id: null, epg_name: null, site: null, status: null, type: null, cluster_name: null, dhcp: null });
const ALL = [HERZI, UPI, FREE_2, MCE, OLD];

const view = (overrides: Partial<SegmentsView>): SegmentsView => ({ ...DEFAULT_VIEW, ...overrides });
const cidrs = (rows: { segment: string }[]) => rows.map((r) => r.segment);

describe("the search", () => {
  it("matches the cluster, EPG, VLAN ID, segment or site, without case", () => {
    expect(matchesSearch(HERZI, "HERZI")).toBe(true);
    expect(matchesSearch(HERZI, "epg_site1_hc")).toBe(true);
    expect(matchesSearch(HERZI, "141")).toBe(true);
    expect(matchesSearch(HERZI, "10.20.44")).toBe(true);
    expect(matchesSearch(HERZI, "site1")).toBe(true);
    expect(matchesSearch(HERZI, "allocated")).toBe(false);
    expect(matchesSearch(HERZI, "  ")).toBe(true);
  });

  it("finds each name of a shared UPI segment", () => {
    expect(matchesSearch(UPI, "upi-b")).toBe(true);
  });

  it("copes with an old record's empty fields", () => {
    expect(matchesSearch(OLD, "10.20.80")).toBe(true);
    expect(matchesSearch(OLD, "null")).toBe(false);
  });
});

describe("the filters", () => {
  it("shows everything by default, in segments-manager's order", () => {
    expect(filterSegments(ALL, DEFAULT_VIEW)).toEqual(ALL);
  });

  it("splits by status; a record without one is Available", () => {
    expect(cidrs(filterSegments(ALL, view({ status: "allocated" })))).toEqual(["10.20.44.0/24", "10.20.60.0/24", "10.20.70.0/24"]);
    expect(cidrs(filterSegments(ALL, view({ status: "available" })))).toEqual(["10.20.52.0/24", "10.20.80.0/24"]);
  });

  it("compares the site without case, as segments-manager does", () => {
    expect(cidrs(filterSegments(ALL, view({ site: "site2" })))).toEqual(["10.20.52.0/24", "10.20.70.0/24"]);
  });

  it("never matches a type on a segment that has none", () => {
    expect(cidrs(filterSegments(ALL, view({ types: ["HC"] })))).toEqual(["10.20.44.0/24"]);
    expect(cidrs(filterSegments(ALL, view({ types: ["HC", "UPI"] })))).toEqual(["10.20.44.0/24", "10.20.60.0/24"]);
  });

  it("matches one holder exactly, a shared list too, never a substring", () => {
    expect(cidrs(filterSegments(ALL, view({ cluster: "ocp4-upi-a" })))).toEqual(["10.20.60.0/24"]);
    expect(filterSegments(ALL, view({ cluster: "ocp4-upi" }))).toEqual([]);
  });

  it("combines every filter with the search", () => {
    expect(cidrs(filterSegments(ALL, view({ status: "allocated", site: "site1", q: "upi" })))).toEqual(["10.20.60.0/24"]);
  });

  it("counts each tab under the other filters", () => {
    expect(statusCounts(ALL, DEFAULT_VIEW)).toEqual({ all: 5, available: 2, allocated: 3 });
    expect(statusCounts(ALL, view({ status: "available", site: "site2" }))).toEqual({ all: 2, available: 1, allocated: 1 });
  });
});

describe("the sort", () => {
  it("compares VLANs as numbers and text naturally", () => {
    const nine = segment({ vlan_id: 9, epg_name: "EPG_9" });
    const ten = segment({ vlan_id: 10, epg_name: "EPG_10" });
    expect(compareSegments(nine, ten, "vlan_id")).toBeLessThan(0);
    expect(compareSegments(nine, ten, "epg_name")).toBeLessThan(0);
    expect(compareSegments(segment({ segment: "10.20.9.0/24" }), segment({ segment: "10.20.10.0/24" }), "segment")).toBeLessThan(0);
  });

  it("sorts either way with empty values last, and keeps ties in order", () => {
    expect(cidrs(sortSegments(ALL, { id: "vlan_id", desc: false }))).toEqual([
      "10.20.70.0/24", "10.20.44.0/24", "10.20.60.0/24", "10.20.52.0/24", "10.20.80.0/24",
    ]);
    expect(cidrs(sortSegments(ALL, { id: "vlan_id", desc: true }))).toEqual([
      "10.20.52.0/24", "10.20.60.0/24", "10.20.44.0/24", "10.20.70.0/24", "10.20.80.0/24",
    ]);
    expect(cidrs(sortSegments(ALL, { id: "status", desc: false }))).toEqual([
      "10.20.44.0/24", "10.20.60.0/24", "10.20.70.0/24", "10.20.52.0/24", "10.20.80.0/24",
    ]);
  });

  it("sorts DHCP Off before On and the cluster by its names", () => {
    expect(cidrs(sortSegments([HERZI, UPI], { id: "dhcp", desc: false }))).toEqual(["10.20.60.0/24", "10.20.44.0/24"]);
    expect(cidrs(sortSegments([UPI, HERZI, MCE], { id: "cluster", desc: false }))).toEqual(["10.20.44.0/24", "10.20.70.0/24", "10.20.60.0/24"]);
  });

  it("keeps segments-manager's order without a sort", () => {
    expect(sortSegments(ALL, null)).toBe(ALL);
  });

  it("filters, then sorts", () => {
    expect(cidrs(shownSegments(ALL, view({ status: "allocated", sort: { id: "vlan_id", desc: true } })))).toEqual([
      "10.20.60.0/24", "10.20.44.0/24", "10.20.70.0/24",
    ]);
  });
});
