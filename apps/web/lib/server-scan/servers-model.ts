/**
 * What the Servers page shows for a view, from the whole fleet: the rows the
 * filters keep in the view's order, the page of them, the dropdowns' counts
 * and the cluster lists (docs/notes/2026-11-13-server-scan-area-api.md §8.8).
 * Pure, over server-scan's functions (`./rows`), so the page is `useMemo` glue.
 *
 * Wingman's one addition, the Model column's value filter, narrows the rows
 * the counts are taken over too, so every number on the page says what
 * ticking it would show; its own popover lists the models of the rows every
 * other filter keeps.
 */

import { applyColumnFilters, hasColumnFilters } from "@/lib/table/column-filters";
import type { ServerRow } from "@/types/server-scan-servers";
import { clusterFacets, dropdownFacetCounts, filterRows, paginate, sortRows, type ClusterFacets, type FacetCounts } from "./rows";
import { rowFilters, type ServersView } from "./servers-view";

/** server-scan's page size. */
const PAGE_SIZE = 50;

/** A row's text in a column with a value filter (Model), as the filter holds it: `""` for none. */
export const columnText = (row: ServerRow, columnId: string): string => (columnId === "model" ? (row.model ?? "") : "");

export interface ServersModel {
  /** The rows every filter but the column filters keeps, sorted: the Model popover's values come from them. */
  base: ServerRow[];
  /** Every row the filters keep, sorted: what the exports hold. */
  matched: ServerRow[];
  /** The page shown. */
  page: { items: ServerRow[]; page: number; pageCount: number };
  facets: FacetCounts;
  clusters: ClusterFacets;
  /** Whether the page has a row with an MCE: the MCE column shows only then, as server-scan's. */
  withMce: boolean;
}

export function serversModel(rows: readonly ServerRow[], view: ServersView, pageSize = PAGE_SIZE): ServersModel {
  const filters = rowFilters(view);
  const pool = hasColumnFilters(view.columns) ? applyColumnFilters(rows, view.columns, columnText) : rows;
  const base = sortRows(filterRows(rows, filters), view.sort, view.sortDesc);
  const matched = applyColumnFilters(base, view.columns, columnText);
  const page = paginate(matched, view.page, pageSize);
  return {
    base,
    matched,
    page,
    facets: dropdownFacetCounts(pool, filters),
    clusters: clusterFacets(pool, filters),
    withMce: page.items.some((row) => row.mce_name !== null),
  };
}
