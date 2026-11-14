/**
 * The Confs page's mocks (docs/notes/2026-11-13-server-scan-area-api.md §10),
 * typed so a shape change fails `tsc`: a made-up hardware catalog in
 * server-scan's own `GET /api/v1/confs` shape, after server-scan's fake
 * catalog: a mapped conf, one with GPUs, an unmapped one whose disk type and
 * memory type were not read, one whose memory scan failed, and a stored conf
 * server-scan could not read.
 */

import type { Page, Route } from "@playwright/test";
import { json } from "./api-handlers";
import { setUpServerScan } from "./server-scan";
import type { Conf, ConfList } from "../../types/server-scan-confs";

function conf(overrides: Partial<Conf>): Conf {
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
    disks: [
      { count: 2, type: "SSD", capacity_tb: 0.48 },
      { count: 2, type: "NVME", capacity_tb: 1.92 },
    ],
    gpus: [],
    gpu_count: 0,
    gpu_vram_gb: 0,
    adapters: [
      { count: 1, ports: 2, speed: 25 },
      { count: 1, ports: 2, speed: 1 },
    ],
    adapter_count: 2,
    ...overrides,
  };
}

export const CONFS: ConfList = {
  items: [
    conf({}),
    conf({
      conf_id: "CONF202",
      part_number: "210-AZYV-G",
      model: "PowerEdge R750",
      cpu: { ...conf({}).cpu, model: "Intel Xeon Platinum 8358", clock_mhz: 2600, max_clock_mhz: 3400 },
      ram: { total_gib: 2048, dimms: 32, per_dimm_gb: 64, type: ["DDR4"] },
      disks: [{ count: 2, type: "SSD", capacity_tb: 0.48 }, { count: 8, type: "NVME", capacity_tb: 7.68 }],
      gpus: [{ count: 8, model: "NVIDIA H200 SXM" }],
      gpu_count: 8,
      gpu_vram_gb: 141,
      adapters: [{ count: 4, ports: 2, speed: 100 }],
      adapter_count: 4,
    }),
    conf({
      conf_id: "CONF-21",
      part_number: null,
      ram: { total_gib: 512, dimms: 16, per_dimm_gb: 32, type: [] },
      disks: [{ count: 2, type: "SSD", capacity_tb: 0.48 }, { count: 2, type: "unknown", capacity_tb: 0.96 }],
      adapters: [{ count: 1, ports: 2, speed: 25 }],
      adapter_count: 1,
    }),
    conf({
      conf_id: "CONF-34",
      part_number: null,
      model: "ProLiant DL380 Gen9",
      cpu: { ...conf({}).cpu, model: "AMD EPYC 7513", vendor: "AMD", clock_mhz: 2600, max_clock_mhz: 3650 },
      ram: { total_gib: 0, dimms: 0, per_dimm_gb: 0, type: [] },
      disks: [],
      adapters: [],
      adapter_count: 0,
    }),
  ],
  unreadable: ["CONF-99"],
};

type Handler = (route: Route) => Promise<void> | void;

/**
 * An admin, the Sites read the top bar makes, and day1's confs route
 * answering `confs`. Returns how many times the confs were read. Register a
 * test's own routes after this: mocks match LIFO.
 */
export async function setUpConfs(
  page: Page,
  { confs = CONFS, viewer = false, sites }: { confs?: ConfList | Handler; viewer?: boolean; sites?: Handler } = {}
): Promise<{ reads: () => number }> {
  let reads = 0;
  await setUpServerScan(page, { viewer, ...(sites ? { sites } : {}) });
  await page.route("**/api/day1/server-scan/confs", (route) => {
    reads += 1;
    return typeof confs === "function" ? confs(route) : json(route, confs);
  });
  return { reads: () => reads };
}
