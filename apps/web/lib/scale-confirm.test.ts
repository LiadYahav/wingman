import { describe, expect, it } from "vitest";
import { addsLine, changeLine, doneLine, leaving, poolsOf } from "./scale-confirm";
import type { ScaleNodePool, ScaleOptions } from "@/types";

const A = "prod-lark-site1-dell-r660-zone-a";
const B = "prod-lark-site1-dell-r660-zone-b";

const pool = (name: string, scale_down_policy: string | null): ScaleNodePool => ({
  index: 0, name, infra_env: name.replace("prod-lark-site1-", ""), replicas: 3, locked_by: null, locked_replicas: null,
  unnamed: null, scale_down_policy,
});

const options = (a: string | null, b: string | null): Pick<ScaleOptions, "nodepools" | "kinds"> => ({
  nodepools: [pool(A, a), pool(B, b)],
  kinds: [{ kind: "dell-r660-zone", nodepools: [A, B], total: 6, locked: [] }],
});

describe("the change, under the title", () => {
  it("is a NodePool's replicas with the difference, or a hardware type's total over its NodePools", () => {
    expect(changeLine("nodepool", 3, 4, 1)).toBe("3 → 4 replicas (+1)");
    expect(changeLine("nodepool", 4, 1, 1)).toBe("4 → 1 replicas (−3)");
    expect(changeLine("kind", 5, 7, 2)).toBe("5 → 7 in total over 2 NodePools; the workflow spreads it");
  });
});

describe("a scale-up", () => {
  it("adds nodes that each take a free server of the hardware, or wait for one", () => {
    expect(addsLine(1, "nodepool")).toBe(
      "Adds 1 node: it takes a free server of the NodePool's hardware; with none free, it waits until one is added."
    );
    expect(addsLine(3, "kind")).toBe(
      "Adds 3 nodes: each takes a free server of this hardware type; with none free, it waits until one is added."
    );
  });

  it("is done when the NodePools show the new size", () => {
    expect(doneLine("nodepool")).toBe("Done when the NodePool shows the new size; new nodes join after they install.");
    expect(doneLine("kind")).toBe("Done when the NodePools show the new sizes; new nodes join after they install.");
  });
});

describe("which nodes a scale-down removes", () => {
  it("names what each policy the workflow knows picks, unhealthy machines first", () => {
    const one = (policy: string | null, count = 1) => leaving(count, [{ nodepool: A, policy }]).text;
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
    expect(leaving(2, [{ nodepool: A, policy: null }])).toEqual({
      text: "Removes 2 nodes, picked at random by CAPI: the day1 file sets no scale-down policy. Unhealthy machines always go first.",
      pools: [],
      refused: false,
    });
  });

  it("shows an unknown policy as is, and that the workflow will refuse it", () => {
    expect(leaving(1, [{ nodepool: A, policy: "newest-first" }])).toEqual({
      text: "Would remove 1 node by the scale-down policy “newest-first”, which the workflow does not know: the workflow will refuse it.",
      pools: [],
      refused: true,
    });
  });

  it("for a hardware type, says one policy once, and each NodePool's when they differ", () => {
    expect(leaving(2, poolsOf({ mode: "kind", target: "dell-r660-zone" }, options("fewest-pods", "fewest-pods"))).text).toBe(
      "Removes 2 nodes; in each NodePool, the nodes running the fewest pods (fewest-pods). Unhealthy machines always go first."
    );
    expect(leaving(1, poolsOf({ mode: "kind", target: "dell-r660-zone" }, options(null, null))).text).toBe(
      "Removes 1 node, picked at random by CAPI: the day1 file sets no scale-down policy for these NodePools. Unhealthy machines always go first."
    );
    const differ = leaving(1, poolsOf({ mode: "kind", target: "dell-r660-zone" }, options("least-utilized", "odd")));
    expect(differ.text).toBe(
      "Removes 1 node; in each NodePool that loses one, its own scale-down policy picks which. Unhealthy machines always go first."
    );
    expect(differ.refused).toBe(false);
    expect(differ.pools).toEqual([
      { nodepool: A, words: "the nodes with the lowest live CPU or memory use (least-utilized)", refused: false },
      { nodepool: B, words: "“odd”, a policy the workflow does not know: it will refuse the run if this NodePool loses a node", refused: true },
    ]);
    expect(leaving(1, poolsOf({ mode: "kind", target: "dell-r660-zone" }, options("fewest-pods", null))).pools[1]).toEqual({
      nodepool: B, words: "picked at random by CAPI (the day1 file sets no policy)", refused: false,
    });
  });
});

describe("the NodePools a change may move", () => {
  it("are the one by name, or those the hardware type selects, with their policies", () => {
    const read = options("fewest-pods", null);
    expect(poolsOf({ mode: "nodepool", target: B }, read)).toEqual([{ nodepool: B, policy: null }]);
    expect(poolsOf({ mode: "kind", target: "dell-r660-zone" }, read)).toEqual([
      { nodepool: A, policy: "fewest-pods" },
      { nodepool: B, policy: null },
    ]);
    expect(poolsOf({ mode: "kind", target: "unknown" }, read)).toEqual([]);
  });
});
