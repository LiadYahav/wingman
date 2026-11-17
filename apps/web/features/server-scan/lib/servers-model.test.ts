import { describe, expect, it } from "vitest";
import { serversModel } from "./servers-model";
import { DEFAULT_VIEW, parseServersView } from "./servers-view";
import { serverRow as row } from "./testing";

const view = (query: string) => parseServersView(new URLSearchParams(query));

const FLEET = Array.from({ length: 120 }, (_, i) =>
  row({
    id: `srv_${i}`,
    name: `srv-${i}`,
    model: i % 3 === 0 ? "R760" : i % 3 === 1 ? "R660" : null,
    vendor: i % 2 === 0 ? "dell" : "hp",
    mce_name: i >= 100 ? "mce-a" : null,
    cluster_name: i >= 100 ? "hosted-1" : null,
  })
);

describe("what the Servers page shows", () => {
  it("pages the sorted rows 50 at a time, clamping the page", () => {
    const first = serversModel(FLEET, DEFAULT_VIEW);
    expect(first.page.items).toHaveLength(50);
    expect([first.page.page, first.page.pageCount]).toEqual([1, 3]);
    expect(first.page.items.slice(0, 3).map((r) => r.name)).toEqual(["srv-0", "srv-1", "srv-2"]);
    expect(serversModel(FLEET, view("page=9")).page.page).toBe(3);
    expect(serversModel(FLEET, view("page=3")).page.items).toHaveLength(20);
  });

  it("exports every row the filters keep, not the page", () => {
    expect(serversModel(FLEET, view("vendor=dell")).matched).toHaveLength(60);
  });

  it("shows the MCE column only when a row on the page has one", () => {
    expect(serversModel(FLEET, DEFAULT_VIEW).withMce).toBe(false);
    expect(serversModel(FLEET, view("page=3")).withMce).toBe(true);
  });

  it("applies the Model column's filter to the rows and to the counts, not to its own values", () => {
    const model = serversModel(FLEET, view("f.model=R760&vendor=dell"));
    expect(model.matched.every((r) => r.model === "R760" && r.vendor === "dell")).toBe(true);
    expect(model.matched).toHaveLength(20);
    // Its popover still lists every model of the rows the other filters keep, the blank too
    expect(new Set(model.base.map((r) => r.model))).toEqual(new Set(["R760", "R660", null]));
    // The vendor counts say what ticking HPE would show under the Model filter
    expect(model.facets.vendor).toEqual({ dell: 20, hp: 20 });
    expect(model.facets.total).toBe(20);
    const blank = serversModel(FLEET, view("f.model="));
    expect(blank.matched.every((r) => r.model === null)).toBe(true);
  });

  it("lists the clusters off the fleet, counted under the other filters", () => {
    const model = serversModel(FLEET, view("vendor=hp"));
    expect(model.clusters.mces).toEqual([{ name: "mce-a", mce: null, count: 10 }]);
    expect(model.clusters.hosted).toEqual([{ name: "hosted-1", mce: "mce-a", count: 10 }]);
  });
});
