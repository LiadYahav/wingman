/**
 * Which segments a view shows, and in what order. Pure: the page reads the
 * whole list once and filters here, so a tab switch is instant and the CSV
 * is exactly what is shown.
 */

import type { Segment } from "@/types/segments";
import { cellText, isAllocated, type ColumnId } from "./columns";
import type { SegmentsView, SortState, StatusTab } from "./view";

/** The original's quick search: site, VLAN ID, EPG name, segment or cluster, without case. */
export function matchesSearch(segment: Segment, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  const fields: ColumnId[] = ["site", "vlan_id", "epg_name", "segment", "cluster"];
  return fields.some((field) => cellText(segment, field).toLowerCase().includes(needle));
}

function matchesStatus(segment: Segment, status: StatusTab): boolean {
  if (status === "all") return true;
  return isAllocated(segment) === (status === "allocated");
}

function matchesSite(segment: Segment, site: string | null): boolean {
  return site === null || (segment.site ?? "").toLowerCase() === site.toLowerCase();
}

/** As segments-manager filters: a type never matches a segment without one (an Available one). */
function matchesTypes(segment: Segment, types: string[]): boolean {
  return types.length === 0 || (segment.type !== null && types.includes(segment.type.toUpperCase()));
}

function matchesCluster(segment: Segment, cluster: string | null): boolean {
  return cluster === null || segment.holders.some((holder) => holder.name === cluster);
}

const matchesMismatch = (segment: Segment, only: boolean) => !only || segment.mismatches.length > 0;

/** The segments `view` shows, in segments-manager's order; `ignoreStatus` for the tabs' counts. */
export function filterSegments(segments: Segment[], view: SegmentsView, { ignoreStatus = false } = {}): Segment[] {
  return segments.filter(
    (s) =>
      (ignoreStatus || matchesStatus(s, view.status)) &&
      matchesSite(s, view.site) &&
      matchesTypes(s, view.types) &&
      matchesCluster(s, view.cluster) &&
      matchesMismatch(s, view.mismatch) &&
      matchesSearch(s, view.q)
  );
}

/** Each status tab's count under the view's other filters. */
export function statusCounts(segments: Segment[], view: SegmentsView): Record<StatusTab, number> {
  const rows = filterSegments(segments, view, { ignoreStatus: true });
  const allocated = rows.filter(isAllocated).length;
  return { all: rows.length, available: rows.length - allocated, allocated };
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

/** Two segments by one column, ascending; an empty value is "less" here and sorted last by `sortSegments`. */
export function compareSegments(a: Segment, b: Segment, column: ColumnId): number {
  if (column === "vlan_id") return (a.vlan_id ?? 0) - (b.vlan_id ?? 0);
  return collator.compare(cellText(a, column), cellText(b, column));
}

/** Sorted by `sort` (stable); empty values last either way. `null` keeps segments-manager's order. */
export function sortSegments(segments: Segment[], sort: SortState | null): Segment[] {
  if (!sort) return segments;
  const empty = (s: Segment) => cellText(s, sort.id) === "";
  const sign = sort.desc ? -1 : 1;
  return segments
    .map((segment, index) => ({ segment, index }))
    .sort((x, y) => {
      const [ex, ey] = [empty(x.segment), empty(y.segment)];
      if (ex !== ey) return ex ? 1 : -1;
      return sign * compareSegments(x.segment, y.segment, sort.id) || x.index - y.index;
    })
    .map(({ segment }) => segment);
}

/** What the table shows: filtered, then sorted. */
export const shownSegments = (segments: Segment[], view: SegmentsView): Segment[] =>
  sortSegments(filterSegments(segments, view), view.sort);
