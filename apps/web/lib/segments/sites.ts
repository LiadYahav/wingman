/**
 * The site cards: segments-manager's per-site counts as the original shows
 * them (allocated out of total, then the allocated count of each type above
 * zero), and when a reading is "updated … ago".
 */

import type { SiteSegmentStats } from "@/types/segments";

export interface SiteCard {
  site: string;
  allocated: number;
  total: number;
  /** Every segment of the site is allocated. */
  full: boolean;
  /** Allocated per type, only the types above zero, in segments-manager's order. */
  types: { type: string; count: number }[];
}

export function siteCard(stats: SiteSegmentStats): SiteCard {
  const allocated = Math.max(0, stats.allocated);
  const total = Math.max(0, stats.total_segments);
  return {
    site: stats.site,
    allocated,
    total,
    full: total > 0 && allocated >= total,
    types: stats.by_type.filter((t) => t.allocated > 0).map((t) => ({ type: t.type, count: t.allocated })),
  };
}

/** `just now`, `12 s ago`, `3 min ago`, `2 h ago`: how long since `then` (ms epoch), at `now`. */
export function updatedAgo(then: number, now: number): string {
  const seconds = Math.max(0, Math.floor((now - then) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds} s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.floor(minutes / 60)} h ago`;
}
