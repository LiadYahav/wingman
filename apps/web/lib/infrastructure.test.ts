import { describe, expect, it } from "vitest";
import type { ClusterStatus, Mce } from "@/types";
import { customerMcesBySite, infrastructureCounts, seedsBySite, strayKvClusters } from "./infrastructure";

const mce = (name: string, site: string, extra: Partial<Mce> = {}): Mce => ({
  name, site, kind: "mce", env: "prod", letter: "a", zone: null, follows_convention: true, naming_problems: [],
  default_mastertag: null, hub_version: null, cluster_count: 0, stray_files: [], problems: [], ...extra,
});
const seed = (name: string, site: string, zone: string) => mce(name, site, { kind: "seed", zone });
const cluster = (name: string, site: string, at: string, kind: "tenant" | "kv" = "tenant") =>
  ({ name, site, mce: at, kind }) as ClusterStatus;

const MCES = [
  mce("ocp4-prod-mce-site2-a", "site2"),
  seed("ocp4-prod-seed-site1-az2-a", "site1", "az2"),
  mce("ocp4-prod-mce-site1-b", "site1"),
  seed("ocp4-prod-seed-site1-az1-a", "site1", "az1"),
  mce("ocp4-prod-mce-site1-a", "site1"),
];
const CLUSTERS = [
  cluster("ocp4-prod-lark-site1", "site1", "ocp4-prod-mce-site1-a"),
  cluster("ocp4-prod-kv-site1-az1-b", "site1", "ocp4-prod-seed-site1-az1-a", "kv"),
  cluster("ocp4-prod-kv-site1-az1-a", "site1", "ocp4-prod-seed-site1-az1-a", "kv"),
  cluster("ocp4-prod-kv-site2-az1-a", "site2", "ocp4-prod-mce-site2-a", "kv"),
];

describe("the Infrastructure workspace's groups (ADR-0067)", () => {
  it("lists the Customer MCEs by site, without the seeds", () => {
    expect(customerMcesBySite(MCES).map((g) => [g.site, g.items.map((m) => m.name)])).toEqual([
      ["site1", ["ocp4-prod-mce-site1-a", "ocp4-prod-mce-site1-b"]],
      ["site2", ["ocp4-prod-mce-site2-a"]],
    ]);
  });

  it("lists each seed with the KV clusters in its folder, and a KV cluster elsewhere apart", () => {
    const groups = seedsBySite(MCES, CLUSTERS);
    expect(groups.map((g) => [g.site, g.items.map((s) => [s.seed.name, s.clusters.map((c) => c.name)])])).toEqual([
      ["site1", [
        ["ocp4-prod-seed-site1-az1-a", ["ocp4-prod-kv-site1-az1-a", "ocp4-prod-kv-site1-az1-b"]],
        ["ocp4-prod-seed-site1-az2-a", []],
      ]],
    ]);
    expect(strayKvClusters(MCES, CLUSTERS).map((c) => c.name)).toEqual(["ocp4-prod-kv-site2-az1-a"]);
  });

  it("counts the MCEs and their sites, the seeds and their zones, and the KV clusters", () => {
    expect(infrastructureCounts(MCES, CLUSTERS)).toEqual({ mces: 3, sites: 2, seeds: 2, zones: 2, kvClusters: 3 });
    expect(infrastructureCounts([], [])).toEqual({ mces: 0, sites: 0, seeds: 0, zones: 0, kvClusters: 0 });
  });
});
