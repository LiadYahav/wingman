/**
 * The Servers page's view, kept in the URL under server-scan's own parameter
 * names (docs/notes/2026-11-13-server-scan-area-api.md §8.1), so a link from
 * the Sites page, a shared link or a refresh lands on the same view. Wingman
 * adds one parameter, the Model column's value filter (`f.model`). Parsing
 * never throws: a value it does not know is dropped, and the default stands.
 *
 * The rules are server-scan's (team-redbull/server-scan at 92146d3,
 * `frontend/src/features/inventory/InventoryPage.tsx`): repeated parameters
 * for several values, `maintenance=true` (or `only`) keeps only servers in
 * maintenance and `exclude` hides them, a filter change goes back to page 1,
 * and the sort is never removed (`name`, ascending, by default).
 */

import { describeFilter, hasColumnFilters, readColumnFilters, writeColumnFilters, type ColumnFilters } from "@/lib/table/column-filters";
import { isSortableField, type RowFilters, type SortableField } from "./rows";

const SERVERS_PATH = "/server-scan/servers";

/** The repeated parameters, each a dropdown's or the cluster sidebar's values. */
export const MULTI_KEYS = [
  "vendor",
  "site_id",
  "source_provider",
  "installation_type",
  "openshift_state",
  "health_overall",
  "mce",
  "cluster",
] as const;
export type MultiKey = (typeof MULTI_KEYS)[number];

/** The six dropdowns' parameters, in server-scan's order; the cluster sidebar's are `mce` and `cluster`. */
const DROPDOWN_KEYS = MULTI_KEYS.slice(0, 6);

/** The toggles, each `true` when on. */
export const FLAG_KEYS = ["stale", "duplicate", "contested", "name_mismatch", "donor"] as const;
export type FlagKey = (typeof FLAG_KEYS)[number];

export type MaintenanceMode = "include" | "only" | "exclude";

/** The columns with Wingman's value filter: Model, the one server-scan cannot filter. */
const COLUMN_FILTER_IDS = ["model"] as const;

export interface ServersView {
  search: string;
  multi: Record<MultiKey, string[]>;
  maintenance: MaintenanceMode;
  flags: Record<FlagKey, boolean>;
  /** Wingman's per-column filters (`f.model`). */
  columns: ColumnFilters;
  sort: SortableField;
  sortDesc: boolean;
  /** 1-based; clamped to the pages there are when shown. */
  page: number;
}

const DEFAULT_SORT: SortableField = "name";

const emptyMulti = (): Record<MultiKey, string[]> =>
  Object.fromEntries(MULTI_KEYS.map((key) => [key, []])) as unknown as Record<MultiKey, string[]>;
const noFlags = (): Record<FlagKey, boolean> => Object.fromEntries(FLAG_KEYS.map((key) => [key, false])) as Record<FlagKey, boolean>;

export const DEFAULT_VIEW: ServersView = {
  search: "",
  multi: emptyMulti(),
  maintenance: "include",
  flags: noFlags(),
  columns: {},
  sort: DEFAULT_SORT,
  sortDesc: false,
  page: 1,
};

function maintenanceMode(raw: string | null): MaintenanceMode {
  if (raw === "true" || raw === "only") return "only";
  return raw === "exclude" ? "exclude" : "include";
}

/** The view a query string describes. */
export function parseServersView(params: Pick<URLSearchParams, "get" | "getAll">): ServersView {
  const unique = (values: string[]) => [...new Set(values.filter((v) => v !== ""))];
  const sort = params.get("sort") ?? "";
  const page = Math.trunc(Number(params.get("page") ?? "1"));
  return {
    search: params.get("search") ?? "",
    multi: Object.fromEntries(MULTI_KEYS.map((key) => [key, unique(params.getAll(key))])) as unknown as Record<MultiKey, string[]>,
    maintenance: maintenanceMode(params.get("maintenance")),
    flags: Object.fromEntries(FLAG_KEYS.map((key) => [key, params.get(key) === "true"])) as Record<FlagKey, boolean>,
    columns: readColumnFilters(params, COLUMN_FILTER_IDS),
    sort: isSortableField(sort) ? sort : DEFAULT_SORT,
    sortDesc: params.get("sort_desc") === "true",
    page: Number.isFinite(page) && page > 1 ? page : 1,
  };
}

/** The query string (no `?`) for a view: defaults left out, always in one order. */
export function serializeServersView(view: ServersView): string {
  const params = new URLSearchParams();
  if (view.search.trim()) params.set("search", view.search);
  for (const key of DROPDOWN_KEYS) for (const value of view.multi[key]) params.append(key, value);
  if (view.maintenance !== "include") params.set("maintenance", view.maintenance === "only" ? "true" : "exclude");
  for (const key of FLAG_KEYS) if (view.flags[key]) params.set(key, "true");
  for (const value of view.multi.mce) params.append("mce", value);
  for (const value of view.multi.cluster) params.append("cluster", value);
  writeColumnFilters(params, view.columns, COLUMN_FILTER_IDS);
  if (view.sort !== DEFAULT_SORT || view.sortDesc) params.set("sort", view.sort);
  if (view.sortDesc) params.set("sort_desc", "true");
  if (view.page > 1) params.set("page", String(view.page));
  return params.toString();
}

/** `/server-scan/servers` with a query (a view's, or a Sites card's filter). */
export function serversHref(query: string | ServersView): string {
  const text = typeof query === "string" ? query : serializeServersView(query);
  return text ? `${SERVERS_PATH}?${text}` : SERVERS_PATH;
}

/** The pure functions' filters for a view (server-scan's `RowFilters`; the column filter is applied apart). */
export function rowFilters(view: ServersView, search: string = view.search): RowFilters {
  const next: RowFilters = {};
  const { multi, flags } = view;
  if (search) next.search = search;
  if (multi.vendor.length) next.vendor = multi.vendor;
  if (multi.site_id.length) next.site_id = multi.site_id;
  if (multi.source_provider.length) next.source_provider = multi.source_provider;
  if (multi.installation_type.length) next.installation_type = multi.installation_type;
  if (multi.openshift_state.length) next.openshift_state = multi.openshift_state;
  if (multi.health_overall.length) next.health = multi.health_overall;
  if (view.maintenance !== "include") next.maintenance = view.maintenance;
  if (flags.stale) next.stale = true;
  if (flags.duplicate) next.duplicate = true;
  if (flags.contested) next.contested = true;
  if (flags.name_mismatch) next.nameMismatch = true;
  if (flags.donor) next.donor = true;
  if (multi.mce.length) next.mce = multi.mce;
  if (multi.cluster.length) next.cluster = multi.cluster;
  return next;
}

/** A filter change: back to page 1, as server-scan. */
export const withChange = (view: ServersView, patch: Partial<ServersView>): ServersView => ({ ...view, ...patch, page: 1 });

/** Tick or untick one value of a repeated parameter. */
export function toggleValue(view: ServersView, key: MultiKey, value: string): ServersView {
  const current = view.multi[key];
  const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
  return withChange(view, { multi: { ...view.multi, [key]: next } });
}

export const setValues = (view: ServersView, key: MultiKey, values: string[]): ServersView =>
  withChange(view, { multi: { ...view.multi, [key]: values } });

export const setFlag = (view: ServersView, key: FlagKey, on: boolean): ServersView =>
  withChange(view, { flags: { ...view.flags, [key]: on } });

/** Whether anything narrows the rows (the sort and the page do not). */
export function isFiltered(view: ServersView): boolean {
  return (
    view.search.trim() !== "" ||
    MULTI_KEYS.some((key) => view.multi[key].length > 0) ||
    view.maintenance !== "include" ||
    FLAG_KEYS.some((key) => view.flags[key]) ||
    hasColumnFilters(view.columns)
  );
}

/** Every filter cleared; the sort stays. */
export const clearFilters = (view: ServersView): ServersView => ({ ...DEFAULT_VIEW, sort: view.sort, sortDesc: view.sortDesc });

/**
 * A header click: the other direction on the sorted column; a new column
 * ascending, State (severity) descending, worst first, as server-scan's
 * table (TanStack's first direction for a non-text column). Never unsorted.
 */
export function nextSort(view: ServersView, field: SortableField): ServersView {
  if (view.sort === field) return { ...view, sortDesc: !view.sortDesc, page: 1 };
  return { ...view, sort: field, sortDesc: field === "health", page: 1 };
}

/** One "Filtered by:" chip: what it says, and the view without it. */
export interface FilterChip {
  key: string;
  label: string;
  remove: (view: ServersView) => ServersView;
}

/** Label lookups for the chips: a site's name, a collector's and a state's words. */
export interface ChipWords {
  site: (id: string) => string;
  source: (value: string) => string;
  state: (value: string) => string;
}

const MULTI_LABEL: Record<MultiKey, string> = {
  vendor: "Vendor",
  site_id: "Site",
  source_provider: "Source",
  installation_type: "Classification",
  openshift_state: "Installation",
  health_overall: "Health",
  mce: "MCE",
  cluster: "Cluster",
};

const FLAG_LABEL: Record<FlagKey, string> = {
  stale: "Stale",
  duplicate: "Duplicate Name",
  contested: "Duplicate Server",
  name_mismatch: "Name mismatch",
  donor: "Donor",
};

function multiChips(view: ServersView, words: ChipWords): FilterChip[] {
  const word = (key: MultiKey, value: string) =>
    key === "site_id" ? words.site(value) : key === "source_provider" ? words.source(value) : key === "openshift_state" ? words.state(value) : value;
  const chip = (key: MultiKey, value: string): FilterChip => ({
    key: `${key}:${value}`,
    label: `${MULTI_LABEL[key]} ${word(key, value)}`,
    remove: (v) => toggleValue(v, key, value),
  });
  return DROPDOWN_KEYS.flatMap((key) => view.multi[key].map((value) => chip(key, value)));
}

/** The active filters as server-scan names them ("Vendor dell", "Maintenance only"), in its order. */
export function filterChips(view: ServersView, words: ChipWords): FilterChip[] {
  const chips: FilterChip[] = [];
  if (view.search.trim()) chips.push({ key: "search", label: `Search "${view.search}"`, remove: (v) => withChange(v, { search: "" }) });
  chips.push(...multiChips(view, words));
  if (view.maintenance !== "include") {
    chips.push({
      key: "maintenance",
      label: view.maintenance === "only" ? "Maintenance only" : "Maintenance hidden",
      remove: (v) => withChange(v, { maintenance: "include" }),
    });
  }
  for (const key of ["mce", "cluster"] as const) {
    for (const value of view.multi[key]) {
      chips.push({ key: `${key}:${value}`, label: `${MULTI_LABEL[key]} ${value}`, remove: (v) => toggleValue(v, key, value) });
    }
  }
  for (const key of FLAG_KEYS) {
    if (view.flags[key]) chips.push({ key, label: FLAG_LABEL[key], remove: (v) => setFlag(v, key, false) });
  }
  const model = view.columns.model;
  if (model) {
    const remove = (v: ServersView) => withChange(v, { columns: Object.fromEntries(Object.entries(v.columns).filter(([id]) => id !== "model")) });
    chips.push({ key: "f.model", label: `Model ${describeFilter(model)}`, remove });
  }
  return chips;
}
