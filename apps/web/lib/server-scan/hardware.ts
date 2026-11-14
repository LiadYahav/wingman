/**
 * The Hardware tab's words and numbers, as server-scan's server page shows
 * them (docs/notes/2026-11-13-server-scan-area-api.md §9.1): memory in binary
 * units, storage in decimal ones (as drives are sold and as a `-10tb` name
 * counts), the drives smallest first, a GPU's or PSU's unread reading as a
 * dash, never a zero; the GPU-derived model hint for a chassis that reported
 * none; and what an unread field (`unread_fields`) shows.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/features/servers/HardwareTab.tsx`,
 * `drives.ts`, `frontend/src/lib/gpuModel.ts` and `frontend/src/components/Reported.tsx`.
 */

import type { GpuInfo, PsuInfo, StorageDrive } from "@/types/server-scan-record";

const DASH = "—";

/** Memory and GPU VRAM are binary: GiB, or MiB below 1 GiB. */
export function formatMemory(bytes: number): string {
  if (bytes <= 0) return "0 B";
  return bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GiB` : `${(bytes / 1024 ** 2).toFixed(0)} MiB`;
}

/** Storage is decimal, as drives are sold and as a `-10tb` server name counts it. */
export function formatStorage(bytes: number): string {
  if (bytes <= 0) return "0 B";
  return bytes >= 1000 ** 4 ? `${(bytes / 1000 ** 4).toFixed(2)} TB` : `${(bytes / 1000 ** 3).toFixed(1)} GB`;
}

/** A PSU's rated and real-time wattage, `" — 800W rated, 245W now"`; nothing when neither was read. */
function psuWattageSummary(psu: Pick<PsuInfo, "capacity_watts" | "power_watts">): string {
  const parts: string[] = [];
  if (psu.capacity_watts != null) parts.push(`${psu.capacity_watts}W rated`);
  if (psu.power_watts != null) parts.push(`${psu.power_watts.toFixed(0)}W now`);
  return parts.length > 0 ? ` — ${parts.join(", ")}` : "";
}

/**
 * Drives smallest first, biggest last. A drive whose capacity was not read
 * sorts after every known one, and equal capacities keep the collector's
 * order (the sort is stable). Returns a copy.
 */
export function sortDrivesByCapacity(drives: readonly StorageDrive[]): StorageDrive[] {
  return [...drives].sort((a, b) => {
    if (a.capacity_bytes === null && b.capacity_bytes === null) return 0;
    if (a.capacity_bytes === null) return 1;
    if (b.capacity_bytes === null) return -1;
    return a.capacity_bytes - b.capacity_bytes;
  });
}

/** A drive's cells, Model to Capacity; an unread one is a dash, never `0 B`. */
export function driveCells(drive: StorageDrive): string[] {
  return [
    drive.model ?? DASH,
    drive.serial ?? DASH,
    drive.media_type,
    drive.capacity_bytes != null ? formatStorage(drive.capacity_bytes) : DASH,
  ];
}

/** The GPU table's columns, but Health (a badge): Vendor to Power, then Firmware. */
export const GPU_COLUMNS = [
  "Vendor", "Model", "Serial", "PCI", "VRAM", "Memory type", "ECC", "Errors (correctable/uncorrectable)", "Temp", "Power",
] as const;

/** A GPU's cells in `GPU_COLUMNS` order, then its firmware; a field the provider could not read is a dash. */
export function gpuCells(gpu: GpuInfo): { cells: string[]; firmware: string } {
  const ecc = gpu.ecc_mode_enabled == null ? DASH : gpu.ecc_mode_enabled ? "On" : "Off";
  return {
    cells: [
      gpu.vendor ?? DASH,
      gpu.model ?? "Unknown model",
      gpu.serial ?? DASH,
      gpu.pci_address ?? DASH,
      gpu.memory_bytes != null ? formatMemory(gpu.memory_bytes) : DASH,
      gpu.memory_type ?? DASH,
      ecc,
      `${gpu.correctable_error_count ?? DASH} / ${gpu.uncorrectable_error_count ?? DASH}`,
      gpu.temperature_celsius != null ? `${gpu.temperature_celsius.toFixed(0)}°C` : DASH,
      gpu.power_watts != null ? `${gpu.power_watts.toFixed(0)}W` : DASH,
    ],
    firmware: gpu.firmware_version ?? DASH,
  };
}

/** A PSU's line: its model (or id), then its wattage. */
export function psuLine(psu: PsuInfo): string {
  return `${psu.model ?? psu.id ?? DASH}${psuWattageSummary(psu)}`;
}

const VENDOR_PREFIX = /^(NVIDIA|AMD|Intel)\s+/;
const CAPACITY_SUFFIX = /\s+\d+GB$/;

/**
 * A short, GPU-derived hint for a server whose own model is unread: "A100"
 * from "NVIDIA A100 80GB", distinct models joined. Display only; `null`
 * with no GPU naming a model.
 */
export function inferredGpuModel(gpus: readonly GpuInfo[]): string | null {
  const names = new Set<string>();
  for (const gpu of gpus) {
    if (gpu.model) names.add(gpu.model.replace(VENDOR_PREFIX, "").replace(CAPACITY_SUFFIX, ""));
  }
  return names.size > 0 ? [...names].join(", ") : null;
}

/** The header's model line: the chassis's own, else "<GPU> (from GPU)", else a dash. */
export function modelLine(model: string | null, gpus: readonly GpuInfo[]): string {
  if (model) return model;
  const inferred = inferredGpuModel(gpus);
  return inferred ? `${inferred} (from GPU)` : DASH;
}

/**
 * What a field the last collection could not read shows: `read` as it is;
 * `not-reported` when nothing was ever read there (the value is the model's
 * zero); `unconfirmed` when an earlier value was carried forward.
 */
export type Reported = "read" | "not-reported" | "unconfirmed";

export function reported(unread: boolean, empty: boolean): Reported {
  if (!unread) return "read";
  return empty ? "not-reported" : "unconfirmed";
}

/** The most recent collection could not read it, and nothing was carried forward. */
export const NOT_READ_TITLE = "The most recent collection could not read this.";
/** Unread this run, carried forward from an earlier one. */
export const STALE_TITLE = "Not confirmed by the most recent collection.";
