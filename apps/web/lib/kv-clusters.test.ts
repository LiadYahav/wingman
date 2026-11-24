import { describe, expect, it } from "vitest";
import type { ClusterStatus } from "@/types";
import { fillingOf, noStandbyWarning, ordinal, zoneChains } from "./kv-clusters";

const SEED = "ocp4-prod-seed-site1-az1-a";

function kv(id: string | null, workers: number, { zone = "az1", problems = [] as string[], name = "" } = {}): ClusterStatus {
  return {
    name: name || `ocp4-prod-kv-site1-${zone}-${id}`,
    site: "site1",
    mce: SEED,
    kind: "kv",
    naming: { follows_convention: id !== null, env: "prod", short_name: "kv", sequence: id, zone, problems: [] },
    kv: { workers, max_workers: 40, zone_problems: problems },
  } as unknown as ClusterStatus;
}

const states = (clusters: ClusterStatus[], zone: string | null = "az1") =>
  zoneChains(clusters, zone).map((chain) => [chain.zone, chain.entries.map((e) => [e.cluster.name.slice(-1), e.place, e.state])]);

describe("a zone's KV clusters in their fill order (ADR-0069, AD33)", () => {
  it("orders oldest first by id letter: full, then the one filling, then the next in line", () => {
    expect(states([kv("c", 0), kv("a", 40), kv("b", 12), kv("d", 41)])).toEqual([
      ["az1", [["a", 1, "full"], ["b", 2, "filling"], ["c", 3, "next"], ["d", 4, "full"]]],
    ]);
  });

  it("keeps a KV cluster whose NodePools miss the zone, or that does not parse, out of the order", () => {
    const wrong = kv("a", 3, { problems: ["nodepool[0] names no zone"] });
    const unparsed = { ...kv("b", 0), kv: null };
    const [chain] = zoneChains([wrong, unparsed, kv("c", 2)], "az1");
    expect(chain.entries.map((e) => [e.cluster.name, e.place])).toEqual([["ocp4-prod-kv-site1-az1-c", 1]]);
    expect(chain.apart.map((c) => c.name)).toEqual(["ocp4-prod-kv-site1-az1-a", "ocp4-prod-kv-site1-az1-b"]);
  });

  it("places a name with no id letter last, and groups by zone when the seed's name gives none", () => {
    const off = kv(null, 1, { name: "ocp4-kubevirt-site1-az1-1" });
    expect(states([off, kv("b", 5)]).at(0)?.[1]).toEqual([["b", 1, "filling"], ["1", 2, "next"]]);
    expect(states([kv("a", 1, { zone: "az2" }), kv("a", 1)], null).map(([zone]) => zone)).toEqual(["az1", "az2"]);
  });

  it("warns a zone with no KV cluster next in line, in each case", () => {
    const [one] = zoneChains([kv("a", 40), kv("b", 39)], "az1");
    expect(fillingOf(one)?.cluster.name).toBe("ocp4-prod-kv-site1-az1-b");
    expect(noStandbyWarning(one)).toBe("When ocp4-prod-kv-site1-az1-b fills up, create-vm has nowhere to put az1's VMs.");
    expect(noStandbyWarning(zoneChains([kv("a", 3), kv("b", 0)], "az1")[0])).toBeNull();
    expect(noStandbyWarning(zoneChains([kv("a", 40)], "az1")[0])).toBe(
      "Every KV cluster here is full: create-vm has nowhere to put az1's VMs."
    );
    expect(noStandbyWarning(zoneChains([], "az1")[0])).toBe("No KV cluster here takes VMs: create-vm has nowhere to put az1's VMs.");
    expect(noStandbyWarning(zoneChains([], null)[0])).toContain("this seed's VMs");
  });

  it("says each place in words", () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22].map(ordinal)).toEqual(["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]);
  });
});
