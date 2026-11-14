/**
 * server-scan's Hardware tab, drives and GPU-model cases at 92146d3
 * (`HardwareTab.test.tsx`, `drives.test.ts`, `gpuModel.test.ts`; decision 18),
 * on the pure functions the tab renders.
 */

import { describe, expect, it } from "vitest";
import type { StorageDrive } from "@/types/server-scan-record";
import {
  driveCells, formatMemory, formatStorage, gpuCells, inferredGpuModel, modelLine, psuLine, reported, sortDrivesByCapacity,
} from "./hardware";
import { gpu } from "./testing";

const drive = (id: string, capacity_bytes: number | null): StorageDrive => ({
  id, model: null, serial: null, media_type: "SSD", capacity_bytes, health: "HEALTHY", health_detail: null,
});
const ids = (drives: StorageDrive[]) => drives.map((d) => d.id);

describe("sizes", () => {
  it("memory is binary, storage decimal; a zero is 0 B", () => {
    expect(formatMemory(256 * 1024 ** 3)).toBe("256.0 GiB");
    expect(formatMemory(512 * 1024 ** 2)).toBe("512 MiB");
    expect(formatMemory(0)).toBe("0 B");
    expect(formatStorage(3.84e12)).toBe("3.84 TB");
    expect(formatStorage(960e9)).toBe("960.0 GB");
    expect(formatStorage(0)).toBe("0 B");
  });
});

describe("drives, smallest first", () => {
  it("puts the smallest drive first and the biggest last", () => {
    expect(ids(sortDrivesByCapacity([drive("big", 4000), drive("small", 480), drive("mid", 960)]))).toEqual(["small", "mid", "big"]);
  });

  it("sorts a drive with an unread capacity after every known one", () => {
    expect(ids(sortDrivesByCapacity([drive("unknown", null), drive("big", 4000), drive("zero", 0)]))).toEqual(["zero", "big", "unknown"]);
  });

  it("keeps the collector's order for equal capacities", () => {
    expect(ids(sortDrivesByCapacity([drive("b", 960), drive("a", 960), drive("c", 480)]))).toEqual(["c", "b", "a"]);
  });

  it("does not modify the array it is given", () => {
    const input = [drive("big", 4000), drive("small", 480)];
    sortDrivesByCapacity(input);
    expect(ids(input)).toEqual(["big", "small"]);
  });

  it("dashes every unread drive field instead of stating a zero", () => {
    expect(driveCells({ ...drive("d1", null), media_type: "UNKNOWN" })).toEqual(["—", "—", "UNKNOWN", "—"]);
  });
});

describe("a GPU field the provider could not read", () => {
  it("is a dash, not a crash", () => {
    const { cells, firmware } = gpuCells(gpu());
    expect(cells[1]).toBe("NVIDIA A100 80GB");
    expect(cells.filter((c) => c === "—").length).toBeGreaterThanOrEqual(6);
    expect(cells[7]).toBe("— / —");
    expect(firmware).toBe("—");
  });

  it("shows what was read, with its units", () => {
    const { cells } = gpuCells(gpu({ memory_bytes: 80 * 1024 ** 3, ecc_mode_enabled: false, temperature_celsius: 41.6, power_watts: 88.2, correctable_error_count: 0, uncorrectable_error_count: 2 }));
    expect(cells.slice(4)).toEqual(["80.0 GiB", "—", "Off", "0 / 2", "42°C", "88W"]);
  });
});

describe("a PSU's own model, rating and state", () => {
  const psu = { id: "PSU1", model: "800W Platinum", serial: "PSU123", health: "UP", health_detail: null, capacity_watts: 800, power_watts: 245 };
  it("names the model with its rating and reading", () => {
    expect(psuLine(psu)).toBe("800W Platinum — 800W rated, 245W now");
  });
  it("falls back to the id, with no stray separator", () => {
    expect(psuLine({ ...psu, id: "PSU2", model: null, capacity_watts: null, power_watts: null })).toBe("PSU2");
    expect(psuLine({ ...psu, model: "UCSC-PSU1-770W", capacity_watts: null, power_watts: 248 })).toBe("UCSC-PSU1-770W — 248W now");
  });
});

describe("the model hint from the GPUs", () => {
  it("strips the vendor prefix and capacity suffix", () => {
    expect(inferredGpuModel([gpu({ model: "NVIDIA A100 80GB" })])).toBe("A100");
  });
  it("keeps a multi-word suffix that isn't a capacity", () => {
    expect(inferredGpuModel([gpu({ model: "NVIDIA H100 NVL 94GB" })])).toBe("H100 NVL");
  });
  it("dedupes identical GPUs and joins distinct ones", () => {
    expect(inferredGpuModel([gpu(), gpu()])).toBe("A100");
    expect(inferredGpuModel([gpu(), gpu({ model: "NVIDIA H100 80GB" })])).toBe("A100, H100");
  });
  it("is null with no GPUs or none carrying a model", () => {
    expect(inferredGpuModel([])).toBeNull();
    expect(inferredGpuModel([gpu({ model: null })])).toBeNull();
  });
  it("the header shows the chassis's model, else the hint, else a dash", () => {
    expect(modelLine("PowerEdge R6515", [gpu()])).toBe("PowerEdge R6515");
    expect(modelLine(null, [gpu()])).toBe("A100 (from GPU)");
    expect(modelLine(null, [])).toBe("—");
  });
});

describe("an unread field", () => {
  it("says Not reported for the zero a collector never read, unconfirmed for a carried value", () => {
    expect(reported(true, true)).toBe("not-reported");
    expect(reported(true, false)).toBe("unconfirmed");
    expect(reported(false, true)).toBe("read");
  });
});
