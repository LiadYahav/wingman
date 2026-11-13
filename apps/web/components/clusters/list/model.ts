/**
 * The clusters list's pure logic: its filters, sort and grouping by owner
 * number. The page (app/(app)/clusters/page.tsx) holds the state and the table.
 */

import { OWNER_KEYS, type OwnerKey } from "@/lib/clusters";
import type { FlavorDisplayState } from "@/lib/flavor-state";
import type { ClusterStatus } from "@/types";

export type SortField = "name" | "site" | "spec" | "mastertag" | "created_at";
export type SortDir = "asc" | "desc";
/** A display state (lib/flavor-state), with both update states under `update`. */
export type DriftFilter = "all" | "in_sync" | "update" | "drifted" | "unknown" | "not_linked";

export const DRIFT_FILTERS: { value: DriftFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "in_sync", label: "In sync" },
  { value: "update", label: "Update" },
  { value: "drifted", label: "Drifted" },
  { value: "unknown", label: "Unknown" },
  { value: "not_linked", label: "No flavor" },
];

/** The filter a display state counts under: an open update MR and an update both are an update. */
export function filterOf(state: FlavorDisplayState): Exclude<DriftFilter, "all"> {
  return state === "update_available" || state === "update_mr_open" ? "update" : state;
}

export type GroupBy = "none" | OwnerKey;

export const OWNER_LABEL: Record<OwnerKey, string> = { merkaz: "Merkaz", anaf: "Anaf", mador: "Mador" };

/** An owner filter's choice for clusters whose file does not set that number. */
export const NO_OWNER = "\u0000none";
/** The filter option that clears it. */
export const ANY_OWNER = "\u0000any";

/** One owner number of a row; `""` when the file has none (an old day1 sends no `owner`). */
export function ownerOf(c: ClusterStatus, key: OwnerKey): string {
  return c.owner?.[key] ?? "";
}

export function compareOwner(a: string, b: string): number {
  if (a === b) return 0;
  if (!a) return 1; // clusters without the number come last
  if (!b) return -1;
  return a.localeCompare(b, undefined, { numeric: true });
}

/** Two clusters in a column's ascending order. */
export function compareBy(field: SortField, a: ClusterStatus, b: ClusterStatus): number {
  switch (field) {
    case "name": return a.name.localeCompare(b.name);
    case "site": return `${a.site}/${a.mce}`.localeCompare(`${b.site}/${b.mce}`);
    case "spec": return (a.spec_name ?? "").localeCompare(b.spec_name ?? "");
    case "mastertag": return (a.mastertag ?? "").localeCompare(b.mastertag ?? "", undefined, { numeric: true });
    case "created_at": return (a.created_at ?? "").localeCompare(b.created_at ?? "");
  }
}

/** Whether a lowercased search finds the cluster: in its name, site, MCE, flavor, mastertag or owner numbers. */
export function matchesSearch(c: ClusterStatus, q: string): boolean {
  return (
    [c.name, c.site, c.mce, c.spec_name ?? "", c.mastertag ?? ""].some((text) => text.toLowerCase().includes(q)) ||
    OWNER_KEYS.some((k) => ownerOf(c, k).includes(q))
  );
}

/** How many items have each key. */
export function countBy<T>(items: T[], keyOf: (item: T) => string): Map<string, number> {
  const counts = new Map<string, number>();
  for (const item of items) counts.set(keyOf(item), (counts.get(keyOf(item)) ?? 0) + 1);
  return counts;
}
