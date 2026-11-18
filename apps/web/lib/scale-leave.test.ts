import { describe, expect, it } from "vitest";
import { leaveFields, leaveLine, leaveReady, overrideOf, overrides, ownPolicy, runChoice } from "./scale-leave";
import type { ScaleNodePool, ScaleResult } from "@/types";

const A = "prod-lark-site1-dell-r660-zone-a";
const B = "prod-lark-site1-dell-r660-zone-b";
const UNHEALTHY = "Unhealthy machines always go first.";

const pool = (name: string, scale_down_policy: string | null): ScaleNodePool => ({
  index: 0, name, infra_env: name.replace("prod-lark-site1-", ""), replicas: 3, locked_by: null, locked_replicas: null,
  unnamed: null, scale_down_policy,
});

const down = (policy: string | null, chosen: ScaleResult["chosen"] = []): ScaleResult => ({
  infra_env_kind: null, nodepool: B, day1_path: null, direction: "down", total_before: 3, total_after: 2,
  nodepools: [{ name: B, infra_env: "dell-r660-zone-b", before: 3, after: 2, scale_down_policy: policy }],
  child_workflow_id: null, revision: null, committed: true, live: [], chosen, deleting: [], ignored: [],
});

describe("the NodePool's own policy", () => {
  it("is the day1 file's for that NodePool, none, or not known", () => {
    const nodepools = [pool(A, "fewest-pods"), pool(B, null)];
    expect(ownPolicy(A, nodepools)).toBe("fewest-pods");
    expect(ownPolicy(B, nodepools)).toBeNull();
    expect(ownPolicy("unknown", nodepools)).toBeUndefined();
  });
});

describe("another policy for this run", () => {
  it("offers the workflow's policies but the NodePool's own, the first by default", () => {
    expect(overrides("fewest-pods")).toEqual(["least-requested", "least-utilized"]);
    expect(overrides(null)).toEqual(["fewest-pods", "least-requested", "least-utilized"]);
    expect(overrides("newest-first")).toEqual(["fewest-pods", "least-requested", "least-utilized"]);
    expect(overrideOf(null, "fewest-pods")).toBe("least-requested");
    expect(overrideOf("least-utilized", "fewest-pods")).toBe("least-utilized");
    expect(overrideOf("fewest-pods", "fewest-pods")).toBe("least-requested");
  });
});

describe("what a start sends", () => {
  it("is nothing for the NodePool's own policy, else exactly one field, and never on a scale-up", () => {
    expect(leaveFields("own", 2, [], "least-utilized")).toEqual({});
    expect(leaveFields("policy", 2, [], "least-utilized")).toEqual({ scale_down_policy: "least-utilized" });
    expect(leaveFields("servers", 2, ["a", "b"], "least-utilized")).toEqual({ server_names: ["a", "b"] });
    expect(leaveFields("policy", 0, [], "least-utilized")).toEqual({});
    expect(leaveFields("servers", 0, ["a"], "least-utilized")).toEqual({});
  });

  it("waits for exactly as many servers as leave, and for nothing else", () => {
    expect(leaveReady("servers", 1, 2)).toBe(false);
    expect(leaveReady("servers", 0, 2)).toBe(false);
    expect(leaveReady("servers", 2, 2)).toBe(true);
    expect(leaveReady("own", 0, 2)).toBe(true);
    expect(leaveReady("policy", 0, 2)).toBe(true);
    expect(leaveReady("servers", 0, 0)).toBe(true);
  });
});

describe("the confirmation's line", () => {
  it("says which nodes leave by the choice", () => {
    expect(leaveLine("own", 1, "fewest-pods", "least-requested", []).text).toBe(`Removes the node running the fewest pods (fewest-pods). ${UNHEALTHY}`);
    expect(leaveLine("policy", 2, "fewest-pods", "least-requested", []).text).toBe(
      `Removes the 2 nodes with the lowest requested CPU or memory (least-requested, for this run only). ${UNHEALTHY}`
    );
    expect(leaveLine("own", 1, "newest-first", "fewest-pods", []).refused).toBe(true);
    expect(leaveLine("policy", 1, "newest-first", "fewest-pods", []).refused).toBe(false);
    expect(leaveLine("servers", 2, null, "fewest-pods", ["a"]).text).toBe("Removes the 2 servers you tick below.");
    expect(leaveLine("servers", 2, null, "fewest-pods", ["a", "b"]).text).toBe(
      "Removes exactly the 2 servers you picked: a, b. The NodePool's scale-down policy is not used."
    );
  });
});

describe("the run's choice", () => {
  it("is by name, the NodePool's own, another, or at random", () => {
    const named = down(null, [{ nodepool: B, machine: "m", node: "n", policy: "named", reason: "named: a", server: "a" }]);
    expect(runChoice(named, "fewest-pods")).toBe("Picked by name.");
    expect(runChoice(down("fewest-pods"), "fewest-pods")).toBe("By fewest-pods, the NodePool's own policy.");
    expect(runChoice(down("least-utilized"), "fewest-pods")).toBe(
      "By least-utilized, not the day1 file's policy (fewest-pods): this run's choice, or one set on the NodePool itself."
    );
    expect(runChoice(down("least-utilized"), null)).toBe(
      "By least-utilized, not the day1 file's policy (none): this run's choice, or one set on the NodePool itself."
    );
    expect(runChoice(down("least-utilized"), undefined)).toBe("By least-utilized.");
    expect(runChoice(down(null), null)).toBe("At random, by CAPI: no scale-down policy.");
    expect(runChoice({ ...down("fewest-pods"), direction: "up" }, "fewest-pods")).toBeNull();
  });
});
