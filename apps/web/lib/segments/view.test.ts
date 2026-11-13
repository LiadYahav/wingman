import { describe, expect, it } from "vitest";
import { DEFAULT_VIEW, clearFilters, isFiltered, nextSort, orderTypes, parseView, serializeView, toggleType, viewHref } from "./view";

const parse = (query: string) => parseView(new URLSearchParams(query));

describe("the view in the URL", () => {
  it("is the default with no query", () => {
    expect(parse("")).toEqual(DEFAULT_VIEW);
    expect(serializeView(DEFAULT_VIEW)).toBe("");
    expect(viewHref(DEFAULT_VIEW)).toBe("/segments");
  });

  it("reads every filter and the sort", () => {
    expect(parse("status=allocated&site=site2&type=upi,HC&q=herzi&cluster=ocp4-upi-a&mismatch=1&sort=-vlan_id")).toEqual({
      status: "allocated",
      site: "site2",
      types: ["HC", "UPI"],
      q: "herzi",
      cluster: "ocp4-upi-a",
      mismatch: true,
      sort: { id: "vlan_id", desc: true },
    });
  });

  it("round-trips, in one canonical order", () => {
    const view = parse("mismatch=1&sort=epg_name&cluster=a b&q=10.20&type=UPI,HC&site=site1&status=available");
    const query = serializeView(view);
    expect(query).toBe("status=available&site=site1&type=HC%2CUPI&q=10.20&cluster=a+b&mismatch=1&sort=epg_name");
    expect(parse(query)).toEqual(view);
  });

  it("drops what it does not know, never throws", () => {
    expect(parse("status=locked&sort=-nope&type=,,%20,a b,&site=%20&cluster=&mismatch=yes")).toEqual(DEFAULT_VIEW);
    expect(parse("sort=-").sort).toBeNull();
  });

  it("keeps the search as typed, and leaves a blank one out", () => {
    expect(parse("q=%20herzi%20").q).toBe(" herzi ");
    expect(serializeView({ ...DEFAULT_VIEW, q: "   " })).toBe("");
  });

  it("orders types as segments-manager does, unknown ones after, each once", () => {
    expect(orderTypes(["hub", "ZETA", "HC", "hc", "ALPHA", "UPI"])).toEqual(["HC", "UPI", "HUB", "ALPHA", "ZETA"]);
  });

  it("knows when it filters, and clears every filter but the sort", () => {
    expect(isFiltered(DEFAULT_VIEW)).toBe(false);
    expect(isFiltered({ ...DEFAULT_VIEW, sort: { id: "site", desc: false } })).toBe(false);
    expect(isFiltered({ ...DEFAULT_VIEW, mismatch: true })).toBe(true);
    const busy = parse("status=available&site=site1&type=HC&q=x&cluster=c&mismatch=1&sort=site");
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

  it("toggles a type in and out", () => {
    const one = toggleType(DEFAULT_VIEW, "UPI");
    const two = toggleType(one, "HC");
    expect(two.types).toEqual(["HC", "UPI"]);
    expect(toggleType(two, "UPI").types).toEqual(["HC"]);
  });
});
