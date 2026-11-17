/**
 * The Server Scan area's Confs page: server-scan's hardware catalog, which
 * day1 passes through typed and in its own shape
 * (docs/notes/2026-11-13-server-scan-area-api.md §10, ADR-0048's 3.29.0
 * amendment). Read only: another system writes server-scan's `confs`
 * collection.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/api/confs.ts`.
 */

// ── GET /api/day1/server-scan/confs (server-scan's GET /api/v1/confs) ─────────

/** One server configuration (spec); the shape is the collection writer's, field for field. */
export interface Conf {
  conf_id: string;
  /** `null` when the conf has no catalog match (an unmapped conf). */
  part_number: string | null;
  model: string;
  cpu: {
    model: string;
    vendor: string | null;
    sockets: number;
    cores_per_cpu: number;
    total_cores_ht: number;
    clock_mhz: number;
    max_clock_mhz: number;
    /** Per CPU, in KB. */
    cache_kb: { l1: number; l2: number; l3: number };
  };
  ram: {
    /** `0` when the memory scan failed. */
    total_gib: number;
    dimms: number;
    per_dimm_gb: number;
    /** `[]` when the DIMM read failed. */
    type: string[];
  };
  /** No drive model is recorded; `type` (`NVME`, `SSD`, …) may be `"unknown"`. */
  disks: { count: number; type: string; capacity_tb: number }[];
  /** Grouped by model; may be `[]` while `gpu_count` is not 0. */
  gpus: { count: number; model: string }[];
  gpu_count: number;
  /** VRAM per GPU; `null` or `0` on a GPU-less conf (the page shows neither). */
  gpu_vram_gb: number | null;
  /** No adapter model is recorded; `speed` is per port, in Gb/s. */
  adapters: { count: number; ports: number; speed: number }[];
  adapter_count: number;
}

export interface ConfList {
  /** Every readable conf, in server-scan's natural `conf_id` order. */
  items: Conf[];
  /** The `conf_id` of each stored document server-scan skipped as unreadable. */
  unreadable: string[];
}
