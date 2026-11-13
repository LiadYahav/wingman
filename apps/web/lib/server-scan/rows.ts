/**
 * Filtering, search, sort, facet counts, the cluster lists and paging over the
 * fleet's rows: pure functions, so the Servers page is `useMemo` glue
 * (docs/notes/2026-11-13-server-scan-area-api.md §8, ADR-0048).
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/features/inventory/rows.ts`,
 * `frontend/src/features/inventory/sorting.ts` and `frontend/src/lib/donor.ts`,
 * with their behaviour unchanged; `rows.test.ts` holds server-scan's cases.
 */

import type { MaintenanceState, ServerRow } from "@/types/server-scan-servers";
import { SEVERITY_ORDER, UNASSIGNED_SITE_ID } from "./vocabulary";

/** The sortable columns. Sorting is in the browser; nothing here reaches day1. */
export const SORTABLE_FIELDS = ["name", "model", "openshift_state", "cluster_name", "mce_name", "health"] as const;
export type SortableField = (typeof SORTABLE_FIELDS)[number];

export const isSortableField = (value: string): value is SortableField => (SORTABLE_FIELDS as readonly string[]).includes(value);

export interface RowFilters {
  search?: string;
  /** Each of these six takes several values (OR within, AND across); empty or unset is "any". */
  vendor?: string[];
  site_id?: string[];
  source_provider?: string[];
  installation_type?: string[];
  openshift_state?: string[];
  health?: string[];
  /** Unset shows servers in maintenance with the rest; "only" keeps just them, "exclude" hides them. */
  maintenance?: "only" | "exclude";
  /** Only servers an install currently holds a lock on. */
  reserved?: true;
  stale?: true;
  duplicate?: true;
  /** OpenShift membership contested between two clusters (`contested_with` set). */
  contested?: true;
  /** Installed under a hostname the vendor manager no longer reports (`openshift_reported_name` set). */
  nameMismatch?: true;
  /** Maintenance whose reason says "donor". */
  donor?: true;
  /** Selected MCEs (OR within); ANDed with every other filter. */
  mce?: string[];
  /** Selected clusters, hosted and UPI alike (OR within). */
  cluster?: string[];
}

/** One sidebar entry: a name and how many rows carry it under the current filters. */
export interface ClusterOption {
  name: string;
  count: number;
  /** The owning MCE for a hosted cluster; null for an MCE itself or a UPI cluster. */
  mce: string | null;
}

export interface ClusterFacets {
  mces: ClusterOption[];
  hosted: ClusterOption[];
  upi: ClusterOption[];
}

export interface FacetCounts {
  total: number;
  vendor: Record<string, number>;
  source_provider: Record<string, number>;
  installation_type: Record<string, number>;
  site_id: Record<string, number>;
  openshift_state: Record<string, number>;
  health: Record<string, number>;
  maintenance: Record<string, number>;
  stale: Record<string, number>;
}

const COLLATOR = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

const HEX_LIKE = /^[0-9a-f:-]+$/i;

/** A maintenance whose reason says "donor" (any case) marks a parts donor. */
export function isDonor(maintenance: MaintenanceState): boolean {
  return maintenance.enabled && /\bdonors?\b/i.test(maintenance.reason ?? "");
}

/**
 * How many rows share each name, over the whole fleet (not a filtered
 * subset, or a pair split by another filter would each look unique).
 */
function nameCounts(rows: readonly ServerRow[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const row of rows) counts.set(row.name, (counts.get(row.name) ?? 0) + 1);
  return counts;
}

const anyOf = (wanted: string[] | undefined, value: string | null) => !wanted?.length || (value !== null && wanted.includes(value));

/** Whether a row passes the six dropdowns. */
function passesDropdowns(row: ServerRow, filters: RowFilters): boolean {
  return (
    anyOf(filters.vendor, row.vendor) &&
    anyOf(filters.site_id, row.site_id ?? UNASSIGNED_SITE_ID) &&
    anyOf(filters.source_provider, row.source_provider) &&
    anyOf(filters.installation_type, row.installation_type) &&
    anyOf(filters.openshift_state, row.openshift_state) &&
    anyOf(filters.health, row.health)
  );
}

/** Whether a row passes the toggles and the cluster sidebar. */
function passesFlags(row: ServerRow, filters: RowFilters): boolean {
  return (
    (filters.maintenance === undefined || (filters.maintenance === "only") === row.maintenance.enabled) &&
    (!filters.reserved || row.reservation.held) &&
    (!filters.stale || row.stale) &&
    (!filters.nameMismatch || row.openshift_reported_name !== null) &&
    (!filters.contested || row.contested_with !== null) &&
    (!filters.donor || isDonor(row.maintenance)) &&
    anyOf(filters.mce, row.mce_name) &&
    anyOf(filters.cluster, row.cluster_name)
  );
}

/** Keep the rows every set filter matches, in input order; `search` is applied last. */
export function filterRows(rows: readonly ServerRow[], filters: RowFilters): ServerRow[] {
  const counts = filters.duplicate ? nameCounts(rows) : null;
  const kept = rows.filter(
    (row) => passesDropdowns(row, filters) && passesFlags(row, filters) && (!counts || (counts.get(row.name) ?? 0) > 1)
  );
  return searchRows(kept, filters.search ?? "");
}

/** Longest regex body the search box accepts, the same cap as server-scan's API search. */
const MAX_REGEX_LENGTH = 64;

export interface SearchMatcher {
  /** True when the row matches; every row matches while `error` is set. */
  test: (row: ServerRow) => boolean;
  /** Why the query is unusable (a bad regex), shown under the box. */
  error: string | null;
}

/** The text fields a search looks at, lowercased; MACs are separate. */
function searchFields(row: ServerRow): string[] {
  const fields = [
    row.name,
    row.model,
    row.serial,
    row.vendor,
    row.site_id,
    row.installation_type,
    row.bmc_host,
    // The MCE an install is headed for, so searching it finds the machines going there
    row.reservation.mce_cluster,
  ];
  return fields.flatMap((f) => (f ? [f.toLowerCase()] : []));
}

function regexMatcher(body: string): SearchMatcher {
  if (body.length > MAX_REGEX_LENGTH) {
    return { test: () => true, error: `Regex is longer than ${MAX_REGEX_LENGTH} characters` };
  }
  let pattern: RegExp;
  try {
    pattern = new RegExp(body, "i");
  } catch (e) {
    return { test: () => true, error: `Invalid regex: ${e instanceof Error ? e.message : String(e)}` };
  }
  return {
    test: (row) => searchFields(row).some((f) => pattern.test(f)) || row.macs.some((mac) => pattern.test(mac)),
    error: null,
  };
}

/**
 * The search box's text as a matcher. Plain text is a case-insensitive
 * substring; `"text"` in quotes must equal a whole field; `/pattern/` is a
 * case-insensitive regular expression. A bad regex keeps every row and says why.
 */
export function parseSearch(query: string): SearchMatcher {
  const raw = query.trim();
  if (!raw) return { test: () => true, error: null };
  const regexBody = /^\/(.+)\/$/.exec(raw)?.[1];
  if (regexBody !== undefined) return regexMatcher(regexBody);

  const exactBody = /^"(.+)"$/.exec(raw)?.[1];
  const exact = exactBody !== undefined;
  const q = (exact ? exactBody : raw).toLowerCase();
  const bare = HEX_LIKE.test(q) ? q.replace(/[:-]/g, "") : null;
  const matches = (field: string, needle: string) => (exact ? field === needle : field.includes(needle));
  return {
    test: (row) =>
      searchFields(row).some((f) => matches(f, q)) ||
      row.macs.some((mac) => matches(mac, q) || (bare !== null && matches(mac.replace(/:/g, ""), bare))),
    error: null,
  };
}

/** Keep the rows the search text matches (`parseSearch`); blank keeps the same array. */
export function searchRows(rows: ServerRow[], query: string): ServerRow[] {
  if (!query.trim()) return rows;
  return rows.filter(parseSearch(query).test);
}

/**
 * A sorted copy, naturally (`srv-2` before `srv-10`), blanks last whichever
 * the direction; `health` by severity (ascending: healthiest first). Ties
 * keep input order.
 */
export function sortRows(rows: readonly ServerRow[], field: SortableField, desc: boolean): ServerRow[] {
  const sign = desc ? -1 : 1;
  if (field === "health") {
    const rank = (row: ServerRow) => SEVERITY_ORDER.length - SEVERITY_ORDER.indexOf(row.health);
    return [...rows].sort((a, b) => sign * (rank(a) - rank(b)));
  }
  return [...rows].sort((a, b) => {
    const av = a[field];
    const bv = b[field];
    if (av === null) return bv === null ? 0 : 1;
    if (bv === null) return -1;
    return sign * COLLATOR.compare(av, bv);
  });
}

function count(counts: Record<string, number>, key: string): void {
  counts[key] = (counts[key] ?? 0) + 1;
}

/** Per-value match counts over the rows given; a value no row has is absent (shown as 0). */
export function facetCounts(rows: readonly ServerRow[]): FacetCounts {
  const facets: FacetCounts = {
    total: rows.length,
    vendor: {},
    source_provider: {},
    installation_type: {},
    site_id: {},
    openshift_state: {},
    health: {},
    maintenance: {},
    stale: {},
  };
  for (const row of rows) {
    count(facets.vendor, row.vendor);
    if (row.source_provider) count(facets.source_provider, row.source_provider);
    count(facets.installation_type, row.installation_type);
    count(facets.site_id, row.site_id ?? UNASSIGNED_SITE_ID);
    count(facets.openshift_state, row.openshift_state);
    count(facets.health, row.health);
    count(facets.maintenance, String(row.maintenance.enabled));
    count(facets.stale, String(row.stale));
  }
  return facets;
}

/** The filter keys the six dropdowns own, with the facet each one counts. */
const DIMENSIONS = [
  ["vendor", "vendor"],
  ["source_provider", "source_provider"],
  ["site_id", "site_id"],
  ["installation_type", "installation_type"],
  ["openshift_state", "openshift_state"],
  ["health", "health"],
] as const;

function without(filters: RowFilters, key: keyof RowFilters): RowFilters {
  const next = { ...filters };
  delete next[key];
  return next;
}

/**
 * The dropdowns' counts: each dimension over the rows every *other* filter
 * leaves, so an option's number is what ticking it would show. `total` and
 * the toggles' counts are over the fully filtered rows; `maintenance` is
 * counted without the maintenance filter.
 */
export function dropdownFacetCounts(rows: readonly ServerRow[], filters: RowFilters): FacetCounts {
  const facets = facetCounts(filterRows(rows, filters));
  for (const [filterKey, facetKey] of DIMENSIONS) {
    facets[facetKey] = facetCounts(filterRows(rows, without(filters, filterKey)))[facetKey];
  }
  facets.maintenance = facetCounts(filterRows(rows, without(filters, "maintenance"))).maintenance;
  return facets;
}

/** One page of rows (1-based), clamping an out-of-range page; the page count is never 0. */
export function paginate<T>(rows: readonly T[], page: number, pageSize: number): { items: T[]; page: number; pageCount: number } {
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(Math.max(1, Math.trunc(page) || 1), pageCount);
  const start = (current - 1) * pageSize;
  return { items: rows.slice(start, start + pageSize), page: current, pageCount };
}

/**
 * The MCE, hosted-cluster and UPI-cluster sidebar, read off the fleet itself:
 * options from the whole fleet (they never disappear as you filter), each
 * count over the rows every *other* filter leaves. A cluster with an MCE on
 * any row is hosted; one with none is UPI. Each list largest first, then by name.
 */
export function clusterFacets(rows: readonly ServerRow[], filters: RowFilters): ClusterFacets {
  const mceCounts: Record<string, number> = {};
  for (const row of filterRows(rows, without(filters, "mce"))) if (row.mce_name) count(mceCounts, row.mce_name);
  const clusterCounts: Record<string, number> = {};
  for (const row of filterRows(rows, without(filters, "cluster"))) if (row.cluster_name) count(clusterCounts, row.cluster_name);

  const clusterMce = new Map<string, string | null>();
  const mces = new Set<string>();
  for (const row of rows) {
    if (row.mce_name) mces.add(row.mce_name);
    if (row.cluster_name) clusterMce.set(row.cluster_name, row.mce_name ?? clusterMce.get(row.cluster_name) ?? null);
  }

  const byCount = (a: ClusterOption, b: ClusterOption) => b.count - a.count || COLLATOR.compare(a.name, b.name);
  const hosted: ClusterOption[] = [];
  const upi: ClusterOption[] = [];
  for (const [name, mce] of clusterMce) (mce ? hosted : upi).push({ name, mce, count: clusterCounts[name] ?? 0 });
  return {
    mces: [...mces].map((name) => ({ name, mce: null, count: mceCounts[name] ?? 0 })).sort(byCount),
    hosted: hosted.sort(byCount),
    upi: upi.sort(byCount),
  };
}
