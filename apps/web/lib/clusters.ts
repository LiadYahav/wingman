import type { ClusterStatus } from "@/types";

/** The owner numbers a cluster file carries (§13 of the flavors v2 API note), in the file's order. */
export const OWNER_KEYS = ["merkaz", "anaf", "mador"] as const;
export type OwnerKey = (typeof OWNER_KEYS)[number];

/**
 * The cluster detail page; an admin's `site`/`mce` pin the file when a name is
 * ambiguous. A viewer's cluster has no `mce` (ADR-0068): its link is its name.
 */
export function clusterHref(c: Pick<ClusterStatus, "name" | "site" | "mce">): string {
  return `/clusters/${encodeURIComponent(c.name)}${clusterQuery(c.site, c.mce)}`;
}

/** Where a cluster is, as a list shows it: `site / mce` for an admin, the site for a viewer (ADR-0068). */
export function placeOf(c: { site: string; mce: string | null }): string {
  return c.mce ? `${c.site} / ${c.mce}` : c.site;
}

/**
 * `?site=&mce=` for the day1 cluster routes, omitting what is unknown (names
 * are unique). Only with an MCE: a viewer's cluster has none and is found by
 * its name, so a viewer's page sends neither.
 */
export function clusterQuery(site: string, mce: string | null): string {
  if (!mce) return "";
  const params = new URLSearchParams();
  if (site) params.set("site", site);
  params.set("mce", mce);
  return `?${params.toString()}`;
}
