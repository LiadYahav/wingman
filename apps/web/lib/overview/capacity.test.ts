import { describe, expect, it } from "vitest";
import type { MceInventory, PoolCount } from "@/types/inventory";
import type { SiteSegmentStats } from "@/types/segments";
import { segmentCapacity, serverCapacity } from "./capacity";

const pool = (infra_env: string | null, available: number): PoolCount => ({
  infra_env, available, usable: available, hardware: [], drawable: infra_env ? 0 : null,
});

const mce = (name: string, overrides: Partial<MceInventory> = {}): MceInventory => ({
  site: "site1", mce: name, known: true, servers: 10, in_clusters: 6, available: 4, usable: 4,
  pools: [], infra_envs: [], infra_envs_error: null, infra_envs_from: "mce", ...overrides,
});

const site = (name: string, total_segments: number, allocated: number): SiteSegmentStats => ({
  site: name, total_segments, allocated, by_type: [],
});

describe("the free servers", () => {
  it("are each known MCE's, in day1's order, its pools the most free first and no InfraEnv last", () => {
    const capacity = serverCapacity([
      mce("b", { usable: 3, pools: [pool(null, 1), pool("small", 1), pool("big", 2), pool("again", 1)] }),
      mce("a", { site: "site2", servers: 4, in_clusters: 4, available: 0, usable: 0 }),
      mce("c", { known: false, servers: 0, in_clusters: 0, available: 0, usable: 0 }),
    ]);
    expect(capacity.free).toBe(4);
    expect(capacity.unknown).toEqual(["c"]);
    expect(capacity.mces).toEqual([
      {
        site: "site1", mce: "b", free: 4, unusable: 1, servers: 10, usedPercent: 60,
        pools: [{ infraEnv: "big", free: 2 }, { infraEnv: "again", free: 1 }, { infraEnv: "small", free: 1 }, { infraEnv: null, free: 1 }],
      },
      { site: "site2", mce: "a", free: 0, unusable: 0, servers: 4, usedPercent: 100, pools: [] },
    ]);
  });

  it("are none before server-scan names a server", () => {
    expect(serverCapacity([])).toEqual({ mces: [], free: 0, unknown: [] });
  });
});

describe("the free segments", () => {
  it("are each site's unallocated ones, in segments-manager's order", () => {
    expect(segmentCapacity([site("site2", 4, 1), site("site1", 5, 5), site("site3", 0, 0)])).toEqual({
      sites: [
        { site: "site2", free: 3, total: 4, usedPercent: 25, full: false },
        { site: "site1", free: 0, total: 5, usedPercent: 100, full: true },
        { site: "site3", free: 0, total: 0, usedPercent: 0, full: false },
      ],
      free: 3,
    });
  });

  it("never count below zero when segments-manager's numbers disagree", () => {
    expect(segmentCapacity([site("site1", 2, 3)]).sites[0]).toMatchObject({ free: 0, usedPercent: 100, full: true });
  });
});
