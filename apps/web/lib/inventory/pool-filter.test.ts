import { describe, expect, it } from "vitest";
import type { PoolCount } from "@/types/inventory";
import {
  NO_FILTER,
  facetsOf,
  narrows,
  parseInfraEnvName,
  poolNames,
  shownPools,
  splitSelection,
  withinFacets,
  type PoolFilter,
} from "./pool-filter";

const pool = (infra_env: string | null, overrides: Partial<PoolCount> = {}): PoolCount => ({
  infra_env, available: 0, usable: 0, hardware: [], ready: 0, needs_fix: 0, total: 0, server_prefix: null,
  label_problems: [], used: [], herzi: { ignored: false, paused: false, blocked_until: null, no_hardware_since: null }, ...overrides,
});

const POOLS = [
  pool("c200-kv32-az2", { available: 1, total: 1 }),
  pool("c200-mtl-az1"),
  pool("c200-kv8-az1", { ready: 2, total: 2 }),
  pool("r760-mtl-az10", { available: 5, total: 5 }),
  pool("dell-r660-site1-128c-1024gb-5tb", { used: ["ocp-x"] }),
  pool(null, { available: 4, total: 4 }),
];

const names = (pools: PoolCount[]) => pools.map((p) => p.infra_env);
const filter = (overrides: Partial<PoolFilter>): PoolFilter => ({ ...NO_FILTER, ...overrides });

describe("an InfraEnv's name", () => {
  it("is read as flavor, size and zone under the platform's convention", () => {
    expect(parseInfraEnvName("c200-mtl-az1")).toEqual({ flavor: "c200", size: "mtl", zone: "az1" });
    expect(parseInfraEnvName("c200-kv32-az2")).toEqual({ flavor: "c200", size: "kv32", zone: "az2" });
  });

  it("off the convention is not guessed", () => {
    for (const name of ["dell-r660-site1-128c-1024gb-5tb", "hp-gen12-site1-64c-512gb", "c200-kv-az1", "c200-gpu-az1", "C200-MTL-AZ1", "c200-mtl"]) {
      expect(parseInfraEnvName(name)).toBeNull();
    }
  });

  it("gives the zones and sizes to filter by, in natural order with their counts; none when nothing parses", () => {
    expect(facetsOf(poolNames(POOLS))).toEqual({
      zone: [{ value: "az1", count: 2 }, { value: "az2", count: 1 }, { value: "az10", count: 1 }],
      size: [{ value: "kv8", count: 1 }, { value: "kv32", count: 1 }, { value: "mtl", count: 2 }],
    });
    expect(facetsOf(["dell-r660-site1-128c-1024gb-5tb"])).toEqual({ zone: [], size: [] });
  });
});

describe("the InfraEnvs picked", () => {
  it("split into those this MCE has and those it lacks, both kept", () => {
    expect(splitSelection(poolNames(POOLS), ["c200-mtl-az1", "g12-mtl-az1"])).toEqual({ present: ["c200-mtl-az1"], missing: ["g12-mtl-az1"] });
    expect(poolNames(POOLS)).not.toContain(null);
  });

  it("narrow the table to them; the servers no one InfraEnv names leave with any name filter", () => {
    expect(names(shownPools(POOLS, ["c200-mtl-az1", "r760-mtl-az10", "g12-mtl-az1"], NO_FILTER))).toEqual(["c200-mtl-az1", "r760-mtl-az10"]);
    expect(names(shownPools(POOLS, [], filter({ search: "KV" })))).toEqual(["c200-kv8-az1", "c200-kv32-az2"]);
  });
});

describe("the table's filters", () => {
  it("show every pool by name, the servers no one InfraEnv names last", () => {
    expect(names(shownPools(POOLS, [], NO_FILTER))).toEqual([
      "c200-kv8-az1", "c200-kv32-az2", "c200-mtl-az1", "dell-r660-site1-128c-1024gb-5tb", "r760-mtl-az10", null,
    ]);
    expect(narrows(NO_FILTER, [])).toBe(false);
  });

  it("combine the zone and the size; a name off the convention is only searchable", () => {
    expect(names(shownPools(POOLS, [], filter({ zone: "az1" })))).toEqual(["c200-kv8-az1", "c200-mtl-az1"]);
    expect(names(shownPools(POOLS, [], filter({ zone: "az1", size: "mtl" })))).toEqual(["c200-mtl-az1"]);
    expect(names(shownPools(POOLS, [], filter({ search: "r660" })))).toEqual(["dell-r660-site1-128c-1024gb-5tb"]);
    expect(narrows(filter({ zone: "az1" }), [])).toBe(true);
  });

  it("keep only the pools with a server, herzi's used Agents included", () => {
    expect(names(shownPools(POOLS, [], filter({ withServers: true })))).toEqual([
      "c200-kv8-az1", "c200-kv32-az2", "dell-r660-site1-128c-1024gb-5tb", "r760-mtl-az10", null,
    ]);
  });

  it("sort by available, most first, then by name", () => {
    expect(names(shownPools(POOLS, [], filter({ sort: "available" })))).toEqual([
      "r760-mtl-az10", "c200-kv32-az2", "c200-kv8-az1", "c200-mtl-az1", "dell-r660-site1-128c-1024gb-5tb", null,
    ]);
    expect(narrows(filter({ sort: "available" }), [])).toBe(false);
  });

  it("drop a zone or size the MCE's names lack", () => {
    const facets = facetsOf(["c200-mtl-az1"]);
    expect(withinFacets(filter({ zone: "az2", size: "mtl" }), facets)).toEqual(filter({ zone: null, size: "mtl" }));
  });
});
