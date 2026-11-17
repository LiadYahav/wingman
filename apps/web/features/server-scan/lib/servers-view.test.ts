import { describe, expect, it } from "vitest";
import {
  DEFAULT_VIEW,
  clearFilters,
  filterChips,
  isFiltered,
  nextSort,
  parseServersView,
  rowFilters,
  serializeServersView,
  serversHref,
  setFlag,
  toggleValue,
  withChange,
} from "./servers-view";

const parse = (query: string) => parseServersView(new URLSearchParams(query));
const roundTrip = (query: string) => serializeServersView(parse(query));
const words = { site: (id: string) => (id === "tlv" ? "Tel Aviv" : id), source: (v: string) => v, state: (v: string) => v };

describe("the Servers view in the URL", () => {
  it("is the default with no query, and no query for the default", () => {
    expect(parse("")).toEqual(DEFAULT_VIEW);
    expect(serializeServersView(DEFAULT_VIEW)).toBe("");
    expect(serversHref(DEFAULT_VIEW)).toBe("/server-scan/servers");
  });

  it("reads server-scan's parameter names, repeated for several values", () => {
    const view = parse(
      "search=r760&vendor=dell&vendor=hp&site_id=tlv&source_provider=OPENMANAGE&installation_type=UPI&openshift_state=AVAILABLE" +
        "&health_overall=CRITICAL&maintenance=true&stale=true&duplicate=true&contested=true&name_mismatch=true&donor=true" +
        "&mce=mce-a&cluster=c1&cluster=c2&f.model=R760&sort=health&sort_desc=true&page=3"
    );
    expect(view.search).toBe("r760");
    expect(view.multi.vendor).toEqual(["dell", "hp"]);
    expect(view.multi.cluster).toEqual(["c1", "c2"]);
    expect(view.maintenance).toBe("only");
    expect(Object.values(view.flags)).toEqual([true, true, true, true, true]);
    expect(view.columns).toEqual({ model: ["R760"] });
    expect([view.sort, view.sortDesc, view.page]).toEqual(["health", true, 3]);
  });

  it("writes one URL per view, in one order, and reads it back the same", () => {
    const query =
      "search=r760&vendor=dell&vendor=hp&site_id=tlv&health_overall=CRITICAL&maintenance=true&stale=true&mce=mce-a&cluster=c1" +
      "&f.model=R760&sort=health&sort_desc=true&page=2";
    expect(roundTrip(query)).toBe(query);
    expect(roundTrip("cluster=c1&vendor=dell")).toBe("vendor=dell&cluster=c1");
  });

  it("reads the Sites cards' filters, maintenance=only and maintenance=exclude", () => {
    expect(parse("site_id=tlv&maintenance=true").maintenance).toBe("only");
    expect(parse("maintenance=only").maintenance).toBe("only");
    expect(parse("maintenance=exclude").maintenance).toBe("exclude");
    expect(roundTrip("maintenance=exclude")).toBe("maintenance=exclude");
    expect(roundTrip("maintenance=only")).toBe("maintenance=true");
  });

  it("drops what it does not know: a sort field, a page, a flag value, a column", () => {
    const view = parse("sort=serial&page=-2&stale=yes&f.vendor=dell&maintenance=maybe&vendor=");
    expect(view).toEqual(DEFAULT_VIEW);
  });

  it("keeps the default sort out of the URL, but a direction in it", () => {
    expect(roundTrip("sort=name")).toBe("");
    expect(roundTrip("sort=name&sort_desc=true")).toBe("sort=name&sort_desc=true");
  });
});

describe("changing the view", () => {
  it("goes back to page 1 on any filter change", () => {
    const view = parse("page=4");
    expect(toggleValue(view, "vendor", "dell").page).toBe(1);
    expect(setFlag(view, "stale", true).page).toBe(1);
    expect(withChange(view, { search: "x" }).page).toBe(1);
  });

  it("ticks and unticks a value", () => {
    const on = toggleValue(DEFAULT_VIEW, "vendor", "dell");
    expect(on.multi.vendor).toEqual(["dell"]);
    expect(toggleValue(on, "vendor", "dell").multi.vendor).toEqual([]);
  });

  it("sorts the other way on the same column, a new one ascending, State worst first; never unsorted", () => {
    const byModel = nextSort(DEFAULT_VIEW, "model");
    expect([byModel.sort, byModel.sortDesc]).toEqual(["model", false]);
    expect(nextSort(byModel, "model").sortDesc).toBe(true);
    expect(nextSort(nextSort(byModel, "model"), "model").sortDesc).toBe(false);
    expect(nextSort(DEFAULT_VIEW, "health").sortDesc).toBe(true);
  });

  it("clears every filter and keeps the sort", () => {
    const view = parse("vendor=dell&f.model=R760&stale=true&search=x&sort=model&sort_desc=true&page=2");
    expect(isFiltered(view)).toBe(true);
    const cleared = clearFilters(view);
    expect(isFiltered(cleared)).toBe(false);
    expect(serializeServersView(cleared)).toBe("sort=model&sort_desc=true");
  });

  it("is the pure functions' filters, the Health dropdown's values as health", () => {
    expect(rowFilters(parse("health_overall=CRITICAL&maintenance=exclude&name_mismatch=true&mce=a"))).toEqual({
      health: ["CRITICAL"],
      maintenance: "exclude",
      nameMismatch: true,
      mce: ["a"],
    });
    expect(rowFilters(parse("search=abc"), "ab")).toEqual({ search: "ab" });
    expect(rowFilters(DEFAULT_VIEW)).toEqual({});
  });
});

describe("the Filtered by chips", () => {
  it("name each filter as server-scan does, in its order", () => {
    const view = parse("search=x&vendor=dell&site_id=tlv&maintenance=true&mce=m&cluster=c&contested=true&f.model=R760");
    expect(filterChips(view, words).map((c) => c.label)).toEqual([
      'Search "x"', "Vendor dell", "Site Tel Aviv", "Maintenance only", "MCE m", "Cluster c", "Duplicate Server", "Model R760",
    ]);
  });

  it("each removes only its own filter", () => {
    const view = parse("vendor=dell&vendor=hp&maintenance=exclude&f.model=R760&donor=true");
    const chips = filterChips(view, words);
    const after = (label: string) => serializeServersView(chips.find((c) => c.label === label)!.remove(view));
    expect(after("Vendor hp")).toBe("vendor=dell&maintenance=exclude&donor=true&f.model=R760");
    expect(after("Maintenance hidden")).toBe("vendor=dell&vendor=hp&donor=true&f.model=R760");
    expect(after("Model R760")).toBe("vendor=dell&vendor=hp&maintenance=exclude&donor=true");
    expect(after("Donor")).toBe("vendor=dell&vendor=hp&maintenance=exclude&f.model=R760");
  });
});
