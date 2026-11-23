import { describe, expect, it } from "vitest";
import type { MceInventory, UnguardedNodepool, UsedLabels } from "@/types/inventory";
import { byCluster, showUnguarded, unguardedHint, unguardedSummary, usedHint } from "./used";

const HERZI: UsedLabels = { keys: ["redbull.io/ever-installed"], source: "herzi" };
const SETTING: UsedLabels = { keys: ["redbull.io/ever-installed"], source: "setting" };

const nodepool = (cluster: string, name: string, replace = false): UnguardedNodepool => ({
  cluster, nodepool: name, infra_envs: ["r650-mtl-az1"], missing: ["redbull.io/ever-installed"], replace,
});

const mce = (overrides: Partial<MceInventory> = {}): MceInventory => ({
  site: "site1", mce: "ocp4-prod-mce-site1-a", known: true, servers: 3, in_clusters: 1, available: 2, usable: 2,
  pools: [], infra_envs: [], infra_envs_error: null, infra_envs_from: "mce", ready: 0, needs_fix: 0, total: 2,
  used: 0, used_error: null, unguarded: [nodepool("ocp4-prod-a-site1", "prod-a-r650")], ...overrides,
});

describe("herzi's used Agents", () => {
  it("are named in the hint, with the label and why they are not available", () => {
    const hint = usedHint(HERZI, ["ocp-r650-mtl-site1-dl1", "ocp-r650-mtl-site1-dl2"]);
    expect(hint).toContain("waiting for herzi to remove: ocp-r650-mtl-site1-dl1, ocp-r650-mtl-site1-dl2.");
    expect(hint).toContain("labelled redbull.io/ever-installed");
    expect(hint).toContain("Not counted as available or in the total.");
    expect(usedHint(HERZI, [])).toContain("waiting for herzi to remove. Each");
  });
});

describe("the NodePools that do not exclude the label", () => {
  it("matter once the deployment excludes it, or herzi has used Agents on the MCE", () => {
    expect(showUnguarded(mce(), HERZI)).toBe(false);
    expect(showUnguarded(mce({ used: 2 }), HERZI)).toBe(true);
    expect(showUnguarded(mce(), SETTING)).toBe(true);
    expect(showUnguarded(mce({ unguarded: [] }), SETTING)).toBe(false);
    expect(showUnguarded(mce({ used: null }), HERZI)).toBe(false);
  });

  it("are grouped by cluster in day1's order and counted", () => {
    const pools = [nodepool("b", "b-1"), nodepool("a", "a-1"), nodepool("b", "b-2", true)];
    expect(byCluster(pools).map((g) => [g.cluster, g.nodepools.map((p) => p.nodepool)])).toEqual([
      ["b", ["b-1", "b-2"]],
      ["a", ["a-1"]],
    ]);
    expect(unguardedSummary(mce({ unguarded: pools }), SETTING)).toBe(
      "3 NodePools in 2 clusters do not exclude redbull.io/ever-installed"
    );
    expect(unguardedSummary(mce(), SETTING)).toBe("1 NodePool in 1 cluster does not exclude redbull.io/ever-installed");
  });

  it("say herzi holds removals until each excludes it, one merge request per cluster", () => {
    const hint = unguardedHint(SETTING);
    expect(hint).toContain("herzi removes a used Agent only once every NodePool that could take it excludes");
    expect(hint).toContain("its own merge request (ADR-0065)");
    expect(hint).toContain("change it to InPlace first");
  });
});
