import { describe, expect, it } from "vitest";
import { addsLine, changeLine, DONE_LINE, leaving, policyOf } from "./scale-confirm";
import type { ScaleNodePool } from "@/types";

const A = "prod-lark-site1-dell-r660-zone-a";
const B = "prod-lark-site1-dell-r660-zone-b";

const pool = (name: string, scale_down_policy: string | null): ScaleNodePool => ({
  index: 0, name, infra_env: name.replace("prod-lark-site1-", ""), replicas: 3, locked_by: null, locked_replicas: null,
  unnamed: null, scale_down_policy,
});

describe("the change, under the title", () => {
  it("is the NodePool's replicas with the difference", () => {
    expect(changeLine(3, 4)).toBe("3 → 4 replicas (+1)");
    expect(changeLine(4, 1)).toBe("4 → 1 replicas (−3)");
  });
});

describe("a scale-up", () => {
  it("adds nodes that each take a free server of the NodePool's hardware, or wait for one", () => {
    expect(addsLine(1)).toBe(
      "Adds 1 node: it takes a free server of the NodePool's hardware; with none free, it waits until one is added."
    );
    expect(addsLine(3)).toBe(
      "Adds 3 nodes: each takes a free server of the NodePool's hardware; with none free, it waits until one is added."
    );
  });

  it("is done when the NodePool shows the new size", () => {
    expect(DONE_LINE).toBe("Done when the NodePool shows the new size; new nodes join after they install.");
  });
});

describe("which nodes a scale-down removes", () => {
  it("names what each policy the workflow knows picks, unhealthy machines first", () => {
    const one = (policy: string | null, count = 1) => leaving(count, policy).text;
    expect(one("fewest-pods")).toBe("Removes the node running the fewest pods (fewest-pods). Unhealthy machines always go first.");
    expect(one("fewest-pods", 2)).toBe("Removes the 2 nodes running the fewest pods (fewest-pods). Unhealthy machines always go first.");
    expect(one("least-requested")).toBe(
      "Removes the node with the lowest requested CPU or memory (least-requested). Unhealthy machines always go first."
    );
    expect(one("least-utilized", 3)).toBe(
      "Removes the 3 nodes with the lowest live CPU or memory use (least-utilized). Unhealthy machines always go first."
    );
  });

  it("says CAPI picks at random when the day1 file sets no policy", () => {
    expect(leaving(2, null)).toEqual({
      text: "Removes 2 nodes, picked at random by CAPI: the day1 file sets no scale-down policy. Unhealthy machines always go first.",
      refused: false,
    });
  });

  it("shows an unknown policy as is, and that the workflow will refuse it", () => {
    expect(leaving(1, "newest-first")).toEqual({
      text: "Would remove 1 node by the scale-down policy “newest-first”, which the workflow does not know: the workflow will refuse it.",
      refused: true,
    });
  });
});

describe("the NodePool's policy", () => {
  it("is the day1 file's for that NodePool, else none", () => {
    const nodepools = [pool(A, "fewest-pods"), pool(B, null)];
    expect(policyOf(A, nodepools)).toBe("fewest-pods");
    expect(policyOf(B, nodepools)).toBeNull();
    expect(policyOf("unknown", nodepools)).toBeNull();
  });
});
