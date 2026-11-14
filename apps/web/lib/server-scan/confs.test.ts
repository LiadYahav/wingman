/**
 * server-scan's Confs page cases at 92146d3 (`ConfsPage.test.tsx`; decision
 * 18), on the pure functions the page renders: its formatting tests as they
 * are, and its page tests' cases where they decide a word or a row.
 */

import { describe, expect, it } from "vitest";
import type { Conf } from "@/types/server-scan-confs";
import {
  adapterText, confsCount, driveCount, formatGhz, formatKb, formatTb, gpuEntries, groupByModel, hasVram, ramTypeText, ramUnread,
  searchText, totalStorageTb, unreadableNotice, visibleConfs,
} from "./confs";

function conf(overrides: Partial<Conf> = {}): Conf {
  return {
    conf_id: "CONF200",
    part_number: "210-AZKL",
    model: "PowerEdge R650",
    cpu: {
      model: "Intel Xeon Gold 6338",
      vendor: "Intel",
      sockets: 2,
      cores_per_cpu: 32,
      total_cores_ht: 128,
      clock_mhz: 2000,
      max_clock_mhz: 3200,
      cache_kb: { l1: 2560, l2: 40960, l3: 49152 },
    },
    ram: { total_gib: 512, dimms: 16, per_dimm_gb: 32, type: ["DDR4"] },
    disks: [{ count: 2, type: "SSD", capacity_tb: 0.48 }],
    gpus: [],
    gpu_count: 0,
    gpu_vram_gb: null,
    adapters: [{ count: 1, ports: 2, speed: 100 }],
    adapter_count: 1,
    ...overrides,
  };
}

const GPU_CONF = conf({ conf_id: "CONF202", gpus: [{ count: 8, model: "NVIDIA H200 SXM" }], gpu_count: 8, gpu_vram_gb: 141 });
const UNMAPPED_CONF = conf({
  conf_id: "CONF-21",
  part_number: null,
  ram: { total_gib: 512, dimms: 16, per_dimm_gb: 32, type: [] },
  disks: [{ count: 2, type: "unknown", capacity_tb: 0.96 }],
});
const ITEMS = [conf(), GPU_CONF, UNMAPPED_CONF];
const ids = (items: Conf[]) => items.map((c) => c.conf_id);

describe("conf formatting", () => {
  it("sums entries per model in first-seen order", () => {
    expect(groupByModel([{ count: 1, model: "B" }, { count: 1, model: "A" }, { count: 1, model: "B" }])).toEqual([
      { model: "B", count: 2 },
      { model: "A", count: 1 },
    ]);
  });

  it("falls back to the GPU count when the writer lists no GPU entries", () => {
    expect(gpuEntries(conf({ gpus: [], gpu_count: 8 }))).toEqual([{ count: 8, model: "unknown" }]);
    expect(gpuEntries(conf())).toEqual([]);
    expect(gpuEntries(GPU_CONF)).toEqual([{ model: "NVIDIA H200 SXM", count: 8 }]);
  });

  it("formats capacities and cache sizes without trailing zeros", () => {
    expect(formatTb(1.92)).toBe("1.92 TB");
    expect(formatTb(8)).toBe("8 TB");
    expect(formatKb(640)).toBe("640 KB");
    expect(formatKb(2560)).toBe("2.5 MB");
    expect(formatKb(49152)).toBe("48 MB");
    expect(formatGhz(2600)).toBe("2.6 GHz");
    expect(formatGhz(2000)).toBe("2.0 GHz");
  });

  it("adds up the drives and their capacity", () => {
    const two = conf({ disks: [{ count: 2, type: "SSD", capacity_tb: 0.48 }, { count: 2, type: "NVME", capacity_tb: 1.92 }] });
    expect(formatTb(totalStorageTb(two))).toBe("4.8 TB");
    expect(driveCount(two)).toBe(4);
    expect(totalStorageTb(conf({ disks: [] }))).toBe(0);
  });

  it("an adapter group reads as count, ports and speed", () => {
    expect(adapterText({ count: 1, ports: 2, speed: 100 })).toBe("1× 2-port 100 Gb/s");
    expect(adapterText({ count: 2, ports: 4, speed: 25 })).toBe("2× 4-port 25 Gb/s");
  });
});

describe("the search", () => {
  it("keeps the API's order and matches every search term", () => {
    expect(ids(visibleConfs(ITEMS, ""))).toEqual(["CONF200", "CONF202", "CONF-21"]);
    expect(ids(visibleConfs(ITEMS, "r650 h200"))).toEqual(["CONF202"]);
  });

  it("filters by any component model, and the count says how many of all", () => {
    const rows = visibleConfs(ITEMS, "h200");
    expect(ids(rows)).toEqual(["CONF202"]);
    expect(confsCount(rows.length, ITEMS.length)).toBe("1 of 3 confs");
    expect(confsCount(ITEMS.length, ITEMS.length)).toBe("3 confs");
  });

  it("looks at ids, part number, model, CPU and its vendor, memory and disk types, GPU models; ignoring case", () => {
    expect(ids(visibleConfs(ITEMS, "210-azkl"))).toEqual(["CONF200", "CONF202"]);
    expect(ids(visibleConfs(ITEMS, "unknown"))).toEqual(["CONF-21"]);
    expect(ids(visibleConfs(ITEMS, "  INTEL   ddr4 "))).toEqual(["CONF200", "CONF202"]);
    expect(searchText(conf())).toContain("intel xeon gold 6338");
    expect(visibleConfs(ITEMS, "nothing-like-it")).toEqual([]);
  });
});

describe("what the page says", () => {
  it("names the unreadable confs, one or several; nothing when all were read", () => {
    expect(unreadableNotice(["CONF-99"])).toBe("1 stored conf could not be read and is not listed:");
    expect(unreadableNotice(["CONF-98", "CONF-99"])).toBe("2 stored confs could not be read and are not listed:");
    expect(unreadableNotice([])).toBeNull();
  });

  it("shows a RAM total of 0 as a failed scan, not 0 GiB", () => {
    expect(ramUnread(conf({ ram: { total_gib: 0, dimms: 0, per_dimm_gb: 0, type: [] } }))).toBe(true);
    expect(ramUnread(conf())).toBe(false);
  });

  it("joins the memory types, and says when none were read", () => {
    expect(ramTypeText(conf())).toBe("DDR4");
    expect(ramTypeText(conf({ ram: { total_gib: 512, dimms: 16, per_dimm_gb: 32, type: ["DDR4", "DDR5"] } }))).toBe("DDR4/DDR5");
    expect(ramTypeText(UNMAPPED_CONF)).toBe("type unread");
  });

  it("hides the GPU line and VRAM of a conf whose GPU fields are stored as 0", () => {
    const noGpu = conf({ gpus: [], gpu_count: 0, gpu_vram_gb: 0 });
    expect(gpuEntries(noGpu)).toEqual([]);
    expect(hasVram(noGpu)).toBe(false);
    expect(hasVram(conf())).toBe(false);
    expect(hasVram(GPU_CONF)).toBe(true);
  });
});
