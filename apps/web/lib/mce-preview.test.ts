import { describe, expect, it } from "vitest";
import type { Mce } from "@/types";
import { firstSite, nextMceLetter, previewMceName, previewSites, siteZones, versionProblem, vmPlan, workersPerZone } from "./mce-preview";

const mce = (name: string, site: string, extra: Partial<Mce> = {}): Mce => ({
  name, site, kind: "mce", env: "prod", letter: null, zone: null, follows_convention: true, naming_problems: [],
  default_mastertag: null, hub_version: null, cluster_count: 0, stray_files: [], problems: [], ...extra,
});
const seed = (name: string, site: string, zone: string | null) => mce(name, site, { kind: "seed", zone, letter: "a" });

const MCES = [
  mce("ocp4-prod-mce-site1-a", "site1", { letter: "a" }),
  mce("ocp4-prep-mce-site1-c", "site1", { letter: "c" }),
  // An off-convention name day1 reads no letter from: its last segment still counts
  mce("ocp4-mce-site1-b", "site1"),
  mce("ocp4-mce-workflow-test", "site1"),
  seed("ocp4-prod-seed-site1-az2-a", "site1", "az2"),
  seed("ocp4-prod-seed-site1-az1-a", "site1", "az1"),
  seed("ocp4-prod-seed-site1-az1-b", "site1", "az1"),
  seed("ocp4-seed-site1", "site1", null),
  mce("ocp4-prod-mce-site10-a", "site10", { letter: "a" }),
  mce("ocp4-prod-mce-site2-a", "site2", { letter: "a" }),
];

describe("the Create Customer MCE preview (ADR-0018's 2026-11-24 amendment)", () => {
  it("offers every site with an MCE-level folder, in natural order", () => {
    expect(previewSites(MCES)).toEqual(["site1", "site2", "site10"]);
  });

  it("takes a site's zones from its seeds, once each, leaving out a seed that names none", () => {
    expect(siteZones(MCES, "site1")).toEqual(["az1", "az2"]);
    expect(siteZones(MCES, "site2")).toEqual([]);
  });

  it("starts on the first site with a seed, else the first site, else none", () => {
    expect(firstSite(MCES)).toBe("site1");
    expect(firstSite([mce("ocp4-prod-mce-site2-a", "site2"), mce("ocp4-prod-mce-site1-a", "site1")])).toBe("site1");
    expect(firstSite([])).toBeNull();
  });

  it("names the next free letter among the site's Customer MCEs, whatever their lifecycle, never a seed's", () => {
    // a, b and c are taken at site1 (the seeds' a and b do not count)
    expect(nextMceLetter(MCES, "site1")).toBe("d");
    expect(previewMceName(MCES, "site1", "test")).toBe("ocp4-test-mce-site1-d");
    expect(previewMceName(MCES, "site2", "prod")).toBe("ocp4-prod-mce-site2-b");
    expect(previewMceName(MCES, "site3", "prep")).toBe("ocp4-prep-mce-site3-a");
  });

  it("has no name once a site's 26 letters are taken", () => {
    const full = [..."abcdefghijklmnopqrstuvwxyz"].map((letter) => mce(`ocp4-prod-mce-site1-${letter}`, "site1", { letter }));
    expect(nextMceLetter(full, "site1")).toBeNull();
    expect(previewMceName(full, "site1", "prod")).toBeNull();
  });

  it("plans one master per zone and the workers in every zone, each VM a kv32", () => {
    expect(vmPlan(3, 1)).toEqual({ masters: 3, workers: 3, vms: 6, vcpu: 192, memoryGiB: 768 });
    expect(vmPlan(2, 2)).toEqual({ masters: 2, workers: 4, vms: 6, vcpu: 192, memoryGiB: 768 });
    expect(vmPlan(0, 1)).toEqual({ masters: 0, workers: 0, vms: 0, vcpu: 0, memoryGiB: 0 });
  });

  it("keeps the workers per zone between one and five", () => {
    expect(workersPerZone(0)).toBe(1);
    expect(workersPerZone(3)).toBe(3);
    expect(workersPerZone(9)).toBe(5);
    expect(workersPerZone(Number.NaN)).toBe(1);
  });

  it("accepts an OpenShift minor or release, and says what one looks like otherwise", () => {
    expect(versionProblem("")).toBeNull();
    expect(versionProblem(" 4.20 ")).toBeNull();
    expect(versionProblem("4.20.44")).toBeNull();
    expect(versionProblem("4.20.44-x86_64")).toBe("An OpenShift version, such as 4.20 or 4.20.44.");
    expect(versionProblem("latest")).toBe("An OpenShift version, such as 4.20 or 4.20.44.");
  });
});
