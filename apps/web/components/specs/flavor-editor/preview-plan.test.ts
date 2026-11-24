import { describe, expect, it } from "vitest";
import type { Mce } from "@/types";
import { previewRelease } from "./preview-plan";

const MCE: Mce = {
  name: "ocp4-prod-mce-site1-a",
  site: "site1",
  kind: "mce",
  env: "prod",
  letter: "a",
  follows_convention: true,
  naming_problems: [],
  default_mastertag: "4.17.58-x86_64",
  hub_version: "4.18.56-x86_64",
  cluster_count: 0,
  stray_files: [],
  problems: [],
};
const OFFERED = ["4.18.56", "4.17.58", "4.16.55"];

describe("the release a flavor's preview renders with", () => {
  it("is the flavor's preset when the MCE offers it, in any architecture", () => {
    expect(previewRelease("4.16.55", MCE, OFFERED)).toBe("4.16.55");
    expect(previewRelease("4.16.55-x86_64", MCE, OFFERED)).toBe("4.16.55");
    expect(previewRelease(" 4.16.55-aarch64 ", MCE, OFFERED)).toBe("4.16.55");
  });

  it("is the MCE's default when the preset is missing or not offered, then the newest offered", () => {
    expect(previewRelease(undefined, MCE, OFFERED)).toBe("4.17.58");
    expect(previewRelease("4.15.9-x86_64", MCE, OFFERED)).toBe("4.17.58");
    expect(previewRelease(undefined, { ...MCE, default_mastertag: "4.21.40-multi" }, OFFERED)).toBe("4.18.56");
    expect(previewRelease(undefined, undefined, OFFERED)).toBe("4.18.56");
  });

  it("is none when the MCE offers nothing", () => {
    expect(previewRelease("4.16.55", MCE, [])).toBeNull();
  });
});
