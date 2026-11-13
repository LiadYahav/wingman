import { describe, expect, it } from "vitest";
import type { ClusterStatus } from "@/types";
import { compareBy, compareOwner, countBy, filterOf, matchesSearch } from "./model";

const cluster = (over: Partial<ClusterStatus>): ClusterStatus =>
  ({ name: "ocp4-prod-a-site1", site: "site1", mce: "mce-prod-1", spec_name: null, mastertag: null, created_at: null, ...over }) as ClusterStatus;

describe("the clusters list model", () => {
  it("finds a cluster by any of its columns, owner numbers included", () => {
    const c = cluster({ spec_name: "Web", mastertag: "4.18.22", owner: { merkaz: "12", anaf: "", mador: "345" } });
    for (const q of ["prod-a", "site1", "mce-prod", "web", "4.18", "345"]) expect(matchesSearch(c, q)).toBe(true);
    expect(matchesSearch(c, "lab")).toBe(false);
  });

  it("sorts mastertags as numbers and puts a cluster without an owner number last", () => {
    const older = cluster({ mastertag: "4.9.1" });
    const newer = cluster({ mastertag: "4.18.0" });
    expect(compareBy("mastertag", older, newer)).toBeLessThan(0);
    expect(compareOwner("", "7")).toBe(1);
    expect(compareOwner("10", "9")).toBeGreaterThan(0);
  });

  it("counts an update and an open update MR under one filter", () => {
    expect(filterOf("update_available")).toBe("update");
    expect(filterOf("update_mr_open")).toBe("update");
    expect(filterOf("drifted")).toBe("drifted");
    expect([...countBy(["a", "b", "a"], (x) => x)]).toEqual([["a", 2], ["b", 1]]);
  });
});
