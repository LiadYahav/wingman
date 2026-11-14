/**
 * What is free to build on: each MCE's free servers by InfraEnv pool
 * (Inventory Management's counts, server-scan's) and each site's free
 * segments (segments-manager's statistics). Pure: the numbers are the
 * sources'; this only orders them and works out the shares.
 */

import { siteCard } from "@/lib/segments/sites";
import type { MceInventory, PoolCount } from "@/types/inventory";
import type { SiteSegmentStats } from "@/types/segments";
import { percent } from "./clusters";

export interface PoolFree {
  /** `null`: free servers whose name matches no InfraEnv on the MCE. */
  infraEnv: string | null;
  free: number;
}

export interface MceCapacity {
  site: string;
  mce: string;
  /** Agents in the MCE's inventory and in no cluster. */
  free: number;
  /** Of those, the ones server-scan says cannot be used now. */
  unusable: number;
  servers: number;
  /** The share of the MCE's servers in a cluster, 0-100. */
  usedPercent: number;
  /** Its pools, the most free first; the servers no InfraEnv names last. */
  pools: PoolFree[];
}

export interface ServerCapacity {
  mces: MceCapacity[];
  free: number;
  /** The MCEs server-scan names no server on: their counts are unknown, not 0. */
  unknown: string[];
}

function byFree(a: PoolCount, b: PoolCount): number {
  if (a.infra_env === null || b.infra_env === null) return a.infra_env === null ? 1 : -1;
  return b.available - a.available || a.infra_env.localeCompare(b.infra_env);
}

/** Each MCE server-scan knows, in day1's order (by site), with its pools. */
export function serverCapacity(mces: readonly MceInventory[]): ServerCapacity {
  const known = mces.filter((m) => m.known);
  return {
    mces: known.map((m) => ({
      site: m.site,
      mce: m.mce,
      free: m.available,
      unusable: Math.max(0, m.available - m.usable),
      servers: m.servers,
      usedPercent: percent(m.in_clusters, m.servers),
      pools: [...m.pools].sort(byFree).map((p) => ({ infraEnv: p.infra_env, free: p.available })),
    })),
    free: known.reduce((total, m) => total + m.available, 0),
    unknown: mces.filter((m) => !m.known).map((m) => m.mce),
  };
}

export interface SiteSegments {
  site: string;
  free: number;
  total: number;
  /** The share of the site's segments allocated, 0-100. */
  usedPercent: number;
  /** Every segment of the site is allocated. */
  full: boolean;
}

/** Each site's free segments, in segments-manager's order, and their sum. */
export function segmentCapacity(stats: readonly SiteSegmentStats[]): { sites: SiteSegments[]; free: number } {
  const sites = stats.map((stat) => {
    const card = siteCard(stat);
    return {
      site: card.site,
      free: Math.max(0, card.total - card.allocated),
      total: card.total,
      usedPercent: percent(card.allocated, card.total),
      full: card.full,
    };
  });
  return { sites, free: sites.reduce((total, s) => total + s.free, 0) };
}
