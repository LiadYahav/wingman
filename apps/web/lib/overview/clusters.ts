/**
 * Where the clusters run and on which OpenShift version, from the clusters
 * list the Overview already reads (the day1 repo's folders and each file's
 * `mastertag`), and how many have an upgrade available or running (the
 * clusters list's own rule, lib/fleet-upgrades.ts). Pure: nothing is read.
 */

import { countUpgrades, openByCluster, rowUpgrade } from "@/lib/fleet-upgrades";
import type { ClusterStatus, FleetUpgrade } from "@/types";

/** `count` as a share of `of`, 0-100: a count above zero is never drawn as nothing. */
export function percent(count: number, of: number): number {
  if (of <= 0 || count <= 0) return 0;
  return Math.min(100, Math.max(2, Math.round((count / of) * 100)));
}

const byCountThenName = <T extends { count: number }>(name: (item: T) => string) => (a: T, b: T) =>
  b.count - a.count || name(a).localeCompare(name(b), undefined, { numeric: true });

export interface MceCount {
  mce: string;
  count: number;
}

export interface SiteCount {
  site: string;
  count: number;
  /** The site's MCEs with clusters, most first. */
  mces: MceCount[];
}

/** The clusters by site and MCE folder, the most first (a tie by name). */
export function clustersBySite(clusters: readonly Pick<ClusterStatus, "site" | "mce">[]): SiteCount[] {
  const sites = new Map<string, Map<string, number>>();
  for (const { site, mce } of clusters) {
    const mces = sites.get(site) ?? new Map<string, number>();
    mces.set(mce, (mces.get(mce) ?? 0) + 1);
    sites.set(site, mces);
  }
  return [...sites].map(([site, mces]) => ({
    site,
    count: [...mces.values()].reduce((a, b) => a + b, 0),
    mces: [...mces].map(([mce, count]) => ({ mce, count })).sort(byCountThenName((m) => m.mce)),
  })).sort(byCountThenName((s) => s.site));
}

export interface VersionCount {
  /** The file's `mastertag`; `null` for the files that set none. */
  version: string | null;
  count: number;
}

export interface VersionSpread {
  /** Newest first, files without a mastertag last. */
  rows: VersionCount[];
  /** What did not fit: how many versions, and their clusters. */
  rest: { versions: number; clusters: number } | null;
}

/** Newest first by each dot-separated number (`4.16.27` above `4.16.9`); no version last. */
function newestFirst(a: VersionCount, b: VersionCount): number {
  if (a.version === null || b.version === null) return a.version === null ? (b.version === null ? 0 : 1) : -1;
  return b.version.localeCompare(a.version, undefined, { numeric: true });
}

/** The clusters by mastertag, the newest `limit` versions shown and the rest summed. */
export function versionSpread(clusters: readonly Pick<ClusterStatus, "mastertag">[], limit = 6): VersionSpread {
  const counts = new Map<string | null, number>();
  for (const { mastertag } of clusters) {
    const version = mastertag?.trim() || null;
    counts.set(version, (counts.get(version) ?? 0) + 1);
  }
  const all = [...counts].map(([version, count]) => ({ version, count })).sort(newestFirst);
  const hidden = all.slice(limit);
  return {
    rows: all.slice(0, limit),
    rest: hidden.length > 0 ? { versions: hidden.length, clusters: hidden.reduce((n, v) => n + v.count, 0) } : null,
  };
}

/**
 * The clusters list's Upgrade filter counts. `off`: upgrades are off here
 * (DAY1_UPGRADES), so nothing is said. `upgrading` is `null` when the
 * fleet's runs could not be read: unknown, not zero.
 */
export type UpgradeSummary = { on: false } | { on: true; available: number; upgrading: number | null };

export function upgradeSummary(
  clusters: readonly Pick<ClusterStatus, "name" | "upgrade_available">[],
  runs: readonly FleetUpgrade[] | null,
  { failed }: { failed: boolean }
): UpgradeSummary {
  const open = openByCluster(runs ?? []);
  const counts = countUpgrades(clusters.map((cluster) => rowUpgrade(cluster, open)));
  const on = runs !== null || failed || counts.available > 0;
  if (!on) return { on: false };
  return { on: true, available: counts.available, upgrading: runs === null ? null : counts.upgrading };
}
