import { describe, expect, it } from "vitest";
import { DEFAULT_VIEW, clearFilters, isFiltered, nextSort, parseView, serializeView, viewHref } from "./view";

const parse = (query: string) => parseView(new URLSearchParams(query));

describe("the view in the URL", () => {
  it("is the default with no query", () => {
    expect(parse("")).toEqual(DEFAULT_VIEW);
    expect(serializeView(DEFAULT_VIEW)).toBe("");
    expect(viewHref(DEFAULT_VIEW)).toBe("/segments");
  });

  it("reads every filter and the sort", () => {
    expect(parse("status=allocated&site=site2&f.type=UPI&f.type=HC&f.dhcp=&q=herzi&cluster=ocp4-upi-a&mismatch=1&sort=-vlan_id")).toEqual({
      status: "allocated",
      site: "site2",
      filters: { type: ["HC", "UPI"], dhcp: [""] },
      q: "herzi",
      cluster: "ocp4-upi-a",
      mismatch: true,
      sort: { id: "vlan_id", desc: true },
    });
  });

  it("round-trips, in one canonical order", () => {
    const view = parse("mismatch=1&sort=epg_name&cluster=a b&q=10.20&f.cluster=ocp4-upi-a, ocp4-upi-b&f.type=UPI&f.type=HC&site=site1&status=available");
    const query = serializeView(view);
    expect(query).toBe(
      "status=available&site=site1&f.type=HC&f.type=UPI&f.cluster=ocp4-upi-a%2C+ocp4-upi-b&q=10.20&cluster=a+b&mismatch=1&sort=epg_name"
    );
    expect(parse(query)).toEqual(view);
  });

  it("reads a link from before the column filters, type=HC,UPI, as the Type column's filter", () => {
    expect(parse("type=upi,HC").filters).toEqual({ type: ["HC", "UPI"] });
    expect(serializeView(parse("type=HC"))).toBe("f.type=HC");
    expect(parse("type=HC&f.type=MCE").filters).toEqual({ type: ["MCE"] });
  });

  it("drops what it does not know, never throws", () => {
    expect(parse("status=locked&sort=-nope&type=,,%20,a b,&f.nope=x&site=%20&cluster=&mismatch=yes")).toEqual(DEFAULT_VIEW);
    expect(parse("sort=-").sort).toBeNull();
  });

  it("keeps the search as typed, and leaves a blank one out", () => {
    expect(parse("q=%20herzi%20").q).toBe(" herzi ");
    expect(serializeView({ ...DEFAULT_VIEW, q: "   " })).toBe("");
  });

  it("knows when it filters, and clears every filter but the sort", () => {
    expect(isFiltered(DEFAULT_VIEW)).toBe(false);
    expect(isFiltered({ ...DEFAULT_VIEW, sort: { id: "site", desc: false } })).toBe(false);
    expect(isFiltered({ ...DEFAULT_VIEW, mismatch: true })).toBe(true);
    expect(isFiltered({ ...DEFAULT_VIEW, filters: { status: ["Available"] } })).toBe(true);
    const busy = parse("status=available&site=site1&f.type=HC&q=x&cluster=c&mismatch=1&sort=site");
    expect(isFiltered(busy)).toBe(true);
    expect(clearFilters(busy)).toEqual({ ...DEFAULT_VIEW, sort: { id: "site", desc: false } });
  });

  it("cycles a column's sort: ascending, descending, off", () => {
    const asc = nextSort(null, "vlan_id");
    expect(asc).toEqual({ id: "vlan_id", desc: false });
    const desc = nextSort(asc, "vlan_id");
    expect(desc).toEqual({ id: "vlan_id", desc: true });
    expect(nextSort(desc, "vlan_id")).toBeNull();
    expect(nextSort(desc, "site")).toEqual({ id: "site", desc: false });
  });
});
