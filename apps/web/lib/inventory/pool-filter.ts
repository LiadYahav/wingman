/**
 * The selected MCE's pool table, narrowed (ADR-0057's 2026-11-24 amendment):
 * to the InfraEnvs picked by name (kept across MCEs), a search on the name,
 * the zone and size the platform's names carry, and pools with servers; sorted
 * by name or by available. Nothing is recounted: the rows are day1's.
 */

import type { PoolCount } from "@/types/inventory";

/** An InfraEnv's name under the platform's convention, `<flavor>-<size>-<zone>`. */
export interface InfraEnvName {
  flavor: string;
  /** `mtl` (bare metal) or `kv<cpu>` (a KubeVirt VM of that many CPUs). */
  size: string;
  zone: string;
}

const CONVENTION = /^([a-z0-9]+)-(mtl|kv[0-9]+)-([a-z0-9]+)$/;

/** `c200-kv32-az2` as its flavor, size and zone; `null` for a name off the convention (`dell-r660-site1-128c-1024gb-5tb`). */
export function parseInfraEnvName(name: string): InfraEnvName | null {
  const match = CONVENTION.exec(name);
  return match ? { flavor: match[1], size: match[2], zone: match[3] } : null;
}

/** The parts of a name the table filters by. */
export type Facet = "zone" | "size";

export interface FacetValue {
  value: string;
  /** The InfraEnvs that have it. */
  count: number;
}

export type Facets = Record<Facet, FacetValue[]>;

const FACETS: readonly Facet[] = ["zone", "size"];

/** `kv8` before `kv32`, `az2` before `az10`. */
const natural = (a: string, b: string) => a.localeCompare(b, "en", { numeric: true });

/** Each zone and size the names carry, with how many have it; nothing for names off the convention. */
export function facetsOf(names: readonly string[]): Facets {
  const counts: Record<Facet, Map<string, number>> = { zone: new Map(), size: new Map() };
  for (const name of names) {
    const parsed = parseInfraEnvName(name);
    if (!parsed) continue;
    for (const facet of FACETS) counts[facet].set(parsed[facet], (counts[facet].get(parsed[facet]) ?? 0) + 1);
  }
  const values = (facet: Facet) =>
    [...counts[facet]].map(([value, count]) => ({ value, count })).sort((a, b) => natural(a.value, b.value));
  return { zone: values("zone"), size: values("size") };
}

export type PoolSort = "name" | "available";

export interface PoolFilter {
  /** A part of the InfraEnv's name, any case. */
  search: string;
  zone: string | null;
  size: string | null;
  /** Only pools with a server: available, ready or needing a fix, or herzi's used Agents. */
  withServers: boolean;
  sort: PoolSort;
}

export const NO_FILTER: PoolFilter = { search: "", zone: null, size: null, withServers: false, sort: "name" };

/** `filter` with a zone or size this MCE's names lack dropped, so a change of MCE never filters by a value it cannot show. */
export function withinFacets(filter: PoolFilter, facets: Facets): PoolFilter {
  const has = (facet: Facet, value: string | null) => value !== null && facets[facet].some((v) => v.value === value);
  return { ...filter, zone: has("zone", filter.zone) ? filter.zone : null, size: has("size", filter.size) ? filter.size : null };
}

/** The InfraEnvs this MCE names: its pools but the servers no one InfraEnv names. */
export const poolNames = (pools: readonly PoolCount[]): string[] =>
  pools.flatMap((pool) => (pool.infra_env === null ? [] : [pool.infra_env]));

/** The selected names this MCE has, and those it lacks (kept in the selection for the MCEs that have them). */
export function splitSelection(names: readonly string[], selection: readonly string[]): { present: string[]; missing: string[] } {
  const here = new Set(names);
  return { present: selection.filter((name) => here.has(name)), missing: selection.filter((name) => !here.has(name)) };
}

/** Whether anything but the order narrows the table. */
export const narrows = (filter: PoolFilter, selection: readonly string[]): boolean =>
  selection.length > 0 || filter.search.trim() !== "" || filter.zone !== null || filter.size !== null || filter.withServers;

const hasServers = (pool: PoolCount) => pool.total > 0 || pool.used.length > 0;

function nameMatches(name: string, picked: ReadonlySet<string>, filter: PoolFilter): boolean {
  if (picked.size > 0 && !picked.has(name)) return false;
  const query = filter.search.trim().toLowerCase();
  if (query && !name.toLowerCase().includes(query)) return false;
  if (filter.zone === null && filter.size === null) return true;
  const parsed = parseInfraEnvName(name);
  return parsed !== null && (filter.zone ?? parsed.zone) === parsed.zone && (filter.size ?? parsed.size) === parsed.size;
}

const byName = (a: PoolCount, b: PoolCount) => natural(a.infra_env ?? "", b.infra_env ?? "");
const byAvailable = (a: PoolCount, b: PoolCount) => b.available - a.available || byName(a, b);

/**
 * The rows the table shows: the named pools that pass every filter, in the
 * chosen order, then the servers no one InfraEnv names, while nothing filters
 * by name (they have none).
 */
export function shownPools(pools: readonly PoolCount[], selection: readonly string[], filter: PoolFilter): PoolCount[] {
  const picked = new Set(selection);
  const kept = (pool: PoolCount) => !filter.withServers || hasServers(pool);
  const named = pools
    .filter((pool) => pool.infra_env !== null && nameMatches(pool.infra_env, picked, filter) && kept(pool))
    .sort(filter.sort === "available" ? byAvailable : byName);
  const byNameFilters = selection.length > 0 || filter.search.trim() !== "" || filter.zone !== null || filter.size !== null;
  const unnamed = byNameFilters ? [] : pools.filter((pool) => pool.infra_env === null && kept(pool));
  return [...named, ...unnamed];
}
