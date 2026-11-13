import type { ClusterStatus } from "@/types";

/** The owner numbers a cluster file carries (§13 of the flavors v2 API note), in the file's order. */
export const OWNER_KEYS = ["merkaz", "anaf", "mador"] as const;
export type OwnerKey = (typeof OWNER_KEYS)[number];

/** The cluster detail page; `site`/`mce` pin the file when a name is ambiguous. */
export function clusterHref(c: Pick<ClusterStatus, "name" | "site" | "mce">): string {
  return `/clusters/${encodeURIComponent(c.name)}?site=${encodeURIComponent(c.site)}&mce=${encodeURIComponent(c.mce)}`;
}

/** `?site=&mce=` for the day1 cluster routes, omitting what is unknown (names are unique). */
export function clusterQuery(site: string, mce: string): string {
  const params = new URLSearchParams();
  if (site) params.set("site", site);
  if (mce) params.set("mce", mce);
  const query = params.toString();
  return query ? `?${query}` : "";
}
