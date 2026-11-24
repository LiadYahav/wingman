/**
 * The Infrastructure workspace's numbers and groups (ADR-0067), from two
 * reads every page there shares: day1's MCE-level folders (`GET
 * /api/day1/mces`, each a Customer MCE or a seed) and the clusters list
 * (each a tenant's or a KV cluster). Pure: nothing is read here.
 */

import { isKvCluster, isSeed } from "@/lib/workspaces";
import type { ClusterStatus, Mce } from "@/types";

const byName = (a: { name: string }, b: { name: string }) =>
  a.name.localeCompare(b.name, undefined, { numeric: true });

const bySiteName = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true });

/** An MCE's servers: Inventory Management opened on that MCE. */
export function mceServersHref(mce: string): string {
  return `/inventory?mce=${encodeURIComponent(mce)}`;
}

/** One site's folders of one kind, sorted by name. */
export interface SiteGroup<T> {
  site: string;
  items: T[];
}

function groupBySite<T>(items: readonly T[], siteOf: (item: T) => string): SiteGroup<T>[] {
  const sites = new Map<string, T[]>();
  for (const item of items) sites.set(siteOf(item), [...(sites.get(siteOf(item)) ?? []), item]);
  return [...sites.keys()].sort(bySiteName).map((site) => ({ site, items: sites.get(site)! }));
}

/** The Customer MCEs, by site: the hubs of the tenants' clusters. */
export function customerMcesBySite(mces: readonly Mce[]): SiteGroup<Mce>[] {
  return groupBySite([...mces].filter((mce) => !isSeed(mce)).sort(byName), (mce) => mce.site);
}

/** A seed and the KV clusters day1 has in its folder, by name. */
export interface SeedWithClusters {
  seed: Mce;
  clusters: ClusterStatus[];
}

/** The seeds, by site, each with its KV clusters. */
export function seedsBySite(mces: readonly Mce[], clusters: readonly ClusterStatus[]): SiteGroup<SeedWithClusters>[] {
  const seeds = [...mces].filter(isSeed).sort(byName);
  const withClusters = seeds.map((seed) => ({
    seed,
    clusters: clusters.filter((c) => isKvCluster(c) && c.site === seed.site && c.mce === seed.name).sort(byName),
  }));
  return groupBySite(withClusters, (entry) => entry.seed.site);
}

/** KV clusters named so under a Customer MCE: create-vm never finds them there. */
export function strayKvClusters(mces: readonly Mce[], clusters: readonly ClusterStatus[]): ClusterStatus[] {
  const seeds = new Set(mces.filter(isSeed).map((seed) => `${seed.site}/${seed.name}`));
  return clusters.filter((c) => isKvCluster(c) && !seeds.has(`${c.site}/${c.mce}`)).sort(byName);
}

export interface InfrastructureCounts {
  mces: number;
  sites: number;
  seeds: number;
  /** The seeds' distinct zones, across sites. */
  zones: number;
  kvClusters: number;
}

/** The Infrastructure Overview's numbers. */
export function infrastructureCounts(mces: readonly Mce[], clusters: readonly ClusterStatus[]): InfrastructureCounts {
  const customer = mces.filter((mce) => !isSeed(mce));
  const seeds = mces.filter(isSeed);
  return {
    mces: customer.length,
    sites: new Set(customer.map((mce) => mce.site)).size,
    seeds: seeds.length,
    zones: new Set(seeds.map((seed) => `${seed.site}/${seed.zone ?? seed.name}`)).size,
    kvClusters: clusters.filter(isKvCluster).length,
  };
}
