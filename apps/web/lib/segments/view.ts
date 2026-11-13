/**
 * The Segments page's view, kept in the URL so a view can be shared and
 * linked (docs/notes/2026-11-13-segments-area-api.md §5): the status tab, the
 * site, the types, the search, one holder and the sort. Parsing never throws:
 * a value it does not know is dropped, and the default stands.
 */

import { SEGMENT_TYPES } from "@/types/segments";
import { isColumnId, type ColumnId } from "./columns";

export const STATUS_TABS = ["all", "available", "allocated"] as const;
export type StatusTab = (typeof STATUS_TABS)[number];

export interface SortState {
  id: ColumnId;
  desc: boolean;
}

export interface SegmentsView {
  status: StatusTab;
  site: string | null;
  /** Upper case, each once, in segments-manager's order (unknown ones after, sorted). */
  types: string[];
  q: string;
  /** Exactly one holder; a shared UPI segment matches when it has it. */
  cluster: string | null;
  /** Only the segments where segments-manager disagrees with a cluster file. */
  mismatch: boolean;
  /** `null`: segments-manager's order. */
  sort: SortState | null;
}

export const DEFAULT_VIEW: SegmentsView = {
  status: "all",
  site: null,
  types: [],
  q: "",
  cluster: null,
  mismatch: false,
  sort: null,
};

const SEGMENTS_PATH = "/segments";

const TYPE_TOKEN = /^[A-Z0-9_-]{1,32}$/;

/** Known types first, in segments-manager's order, then any other, sorted; each once. */
export function orderTypes(types: Iterable<string>): string[] {
  const unique = [...new Set([...types].map((t) => t.trim().toUpperCase()).filter((t) => TYPE_TOKEN.test(t)))];
  const known = SEGMENT_TYPES.filter((t) => unique.includes(t));
  const other = unique.filter((t) => !(SEGMENT_TYPES as readonly string[]).includes(t)).sort();
  return [...known, ...other];
}

function parseSort(raw: string | null): SortState | null {
  if (!raw) return null;
  const desc = raw.startsWith("-");
  const id = desc ? raw.slice(1) : raw;
  return isColumnId(id) ? { id, desc } : null;
}

function text(raw: string | null): string | null {
  const value = raw?.trim();
  return value ? value : null;
}

/** The view a query string describes. */
export function parseView(params: Pick<URLSearchParams, "get">): SegmentsView {
  const status = params.get("status");
  return {
    status: (STATUS_TABS as readonly string[]).includes(status ?? "") ? (status as StatusTab) : "all",
    site: text(params.get("site")),
    types: orderTypes((params.get("type") ?? "").split(",")),
    q: params.get("q") ?? "",
    cluster: text(params.get("cluster")),
    mismatch: params.get("mismatch") === "1",
    sort: parseSort(params.get("sort")),
  };
}

/** The query string (no `?`) for a view: defaults left out, always in one order. */
export function serializeView(view: SegmentsView): string {
  const params = new URLSearchParams();
  if (view.status !== "all") params.set("status", view.status);
  if (view.site) params.set("site", view.site);
  const types = orderTypes(view.types);
  if (types.length > 0) params.set("type", types.join(","));
  if (view.q.trim()) params.set("q", view.q);
  if (view.cluster) params.set("cluster", view.cluster);
  if (view.mismatch) params.set("mismatch", "1");
  if (view.sort) params.set("sort", `${view.sort.desc ? "-" : ""}${view.sort.id}`);
  return params.toString();
}

/** `/segments` with the view's query. */
export function viewHref(view: SegmentsView): string {
  const query = serializeView(view);
  return query ? `${SEGMENTS_PATH}?${query}` : SEGMENTS_PATH;
}

/** Whether anything narrows the rows (the sort does not). */
export function isFiltered(view: SegmentsView): boolean {
  return (
    view.status !== "all" ||
    view.site !== null ||
    view.types.length > 0 ||
    view.q.trim() !== "" ||
    view.cluster !== null ||
    view.mismatch
  );
}

/** The view with every filter cleared; the sort stays. */
export const clearFilters = (view: SegmentsView): SegmentsView => ({ ...DEFAULT_VIEW, sort: view.sort });

/** A header click: ascending, then descending, then segments-manager's order. */
export function nextSort(current: SortState | null, id: ColumnId): SortState | null {
  if (current?.id !== id) return { id, desc: false };
  return current.desc ? null : { id, desc: true };
}

/** The type row's toggle: add a type, or remove it. */
export function toggleType(view: SegmentsView, type: string): SegmentsView {
  const has = view.types.includes(type);
  return { ...view, types: orderTypes(has ? view.types.filter((t) => t !== type) : [...view.types, type]) };
}
