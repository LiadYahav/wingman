import { describe, expect, it } from "vitest";
import { clusterHref, clusterQuery, placeOf } from "./clusters";

const MCE = "ocp4-prod-mce-site1-a";

describe("a cluster's link and reads (ADR-0068)", () => {
  it("pin an admin's cluster by its site and MCE", () => {
    expect(clusterHref({ name: "ocp4-prod-lark-site1", site: "site1", mce: MCE })).toBe(
      `/clusters/ocp4-prod-lark-site1?site=site1&mce=${MCE}`
    );
    expect(clusterQuery("site1", MCE)).toBe(`?site=site1&mce=${MCE}`);
  });

  it("are a viewer's cluster's name alone: it has no MCE, and day1 finds it by its name", () => {
    expect(clusterHref({ name: "ocp4-prod-lark-site1", site: "site1", mce: null })).toBe("/clusters/ocp4-prod-lark-site1");
    expect(clusterQuery("site1", null)).toBe("");
    expect(clusterQuery("site1", "")).toBe("");
  });

  it("say where a cluster is: the site and MCE for an admin, the site for a viewer", () => {
    expect(placeOf({ site: "site1", mce: MCE })).toBe(`site1 / ${MCE}`);
    expect(placeOf({ site: "site1", mce: null })).toBe("site1");
  });
});
