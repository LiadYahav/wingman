/**
 * Every link into segments-manager's data is built here, so a link can become
 * Wingman's own page in one place (ADR-0047). Today: an admin with the
 * Segments area opens `/segments` filtered; everyone else opens
 * segments-manager's UI and its search, whose URLs day1 builds (ADR-0039).
 */

import type { SegmentsManagerLinks } from "@/types";
import { DEFAULT_VIEW, viewHref } from "./view";

/** `/segments` showing one cluster's segments (exactly that holder, a shared UPI list too). */
export const clusterSegmentsHref = (cluster: string): string => viewHref({ ...DEFAULT_VIEW, cluster });

export type SegmentsLink =
  | { kind: "native"; href: string }
  | { kind: "external"; url: string; searchUrl: string };

/**
 * Where a cluster's "its segments" link goes. `area` is whether this person
 * has the Segments area (an admin, segments-manager configured), `undefined`
 * while that is still being found out; `external` is day1's
 * `segments_manager`, `null` when segments-manager is not configured.
 * `null`: no link (yet).
 */
export function clusterSegmentsLink(
  cluster: string,
  { area, external }: { area: boolean | undefined; external: SegmentsManagerLinks | null }
): SegmentsLink | null {
  if (!external) return null;
  if (area === undefined) return null;
  if (area) return { kind: "native", href: clusterSegmentsHref(cluster) };
  return { kind: "external", url: external.url, searchUrl: external.search_url };
}
