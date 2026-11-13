/**
 * Excel-style value filters on a table's columns, as segments-manager's UI
 * has them: each column's header lists the column's distinct values with
 * checkboxes, and a filter keeps the rows whose cell is one of the values
 * kept. Pure, so the caller keeps the filters where it keeps its other state
 * (the URL) and filters its rows, its counts and its exports the same way.
 * The shared `DataTable` draws the header buttons and popovers
 * (`components/data-table/column-filter.tsx`).
 *
 * A column's filter is the list of values it keeps, each a cell's text, `""`
 * for a blank cell; a column without an entry keeps every row. A filter
 * never keeps nothing: the popover cannot apply an empty choice.
 */

/** Per column id, the values kept. */
export type ColumnFilters = Readonly<Record<string, readonly string[]>>;

/** How a list names the blank value (`""`), as the original does. */
export const BLANK_LABEL = "(Blank)";

/** A column's URL parameter: `f.<column id>`, once per value kept (an empty one is the blank). */
const PARAM_PREFIX = "f.";

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

/** Natural order without case, as the original sorts its options (ties by code point, so the order is total). */
const compareValues = (a: string, b: string) => collator.compare(a, b) || (a < b ? -1 : a > b ? 1 : 0);

/** Each value once, sorted naturally; the blank last, as Excel lists it. */
export function sortValues(values: Iterable<string>): string[] {
  const unique = [...new Set(values)];
  const blank = unique.includes("");
  const sorted = unique.filter((v) => v !== "").sort(compareValues);
  return blank ? [...sorted, ""] : sorted;
}

/** A column's distinct values over `rows`, sorted. */
export function distinctValues<T>(rows: readonly T[], text: (row: T) => string): string[] {
  return sortValues(rows.map(text));
}

/**
 * The values a column's popover lists: those of the rows it lists from, and
 * any the filter keeps that none of them has now (another filter, or a shared
 * link, hides it), so it can still be unchecked.
 */
export const filterOptions = (values: readonly string[], kept: readonly string[] | undefined): string[] =>
  sortValues([...values, ...(kept ?? [])]);

/** The rows every column's filter keeps, in their order. `text` is a row's cell in a column, as the filters hold it. */
export function applyColumnFilters<T>(rows: readonly T[], filters: ColumnFilters, text: (row: T, columnId: string) => string): T[] {
  const active = Object.entries(filters).map(([id, values]) => [id, new Set(values)] as const);
  return rows.filter((row) => active.every(([id, kept]) => kept.has(text(row, id))));
}

/**
 * The filters once a column's popover is applied (`kept`) or cleared
 * (`null`). Keeping every value it listed is no filter at all, as in the
 * original, and so is keeping none (the popover never applies that).
 */
export function setColumnFilter(
  filters: ColumnFilters,
  columnId: string,
  kept: readonly string[] | null,
  options: readonly string[]
): ColumnFilters {
  const rest = Object.fromEntries(Object.entries(filters).filter(([id]) => id !== columnId));
  if (kept === null || kept.length === 0 || options.every((option) => kept.includes(option))) return rest;
  return { ...rest, [columnId]: sortValues(kept) };
}

export const hasColumnFilters = (filters: ColumnFilters): boolean => Object.keys(filters).length > 0;

/** The filters a query string holds, for the columns given; any other `f.` parameter is ignored. */
export function readColumnFilters(params: Pick<URLSearchParams, "getAll">, columnIds: readonly string[]): ColumnFilters {
  const filters: Record<string, string[]> = {};
  for (const id of columnIds) {
    const values = params.getAll(`${PARAM_PREFIX}${id}`);
    if (values.length > 0) filters[id] = sortValues(values);
  }
  return filters;
}

/** Appends the filters to `params`, in the columns' order and each column's values sorted, so a view has one URL. */
export function writeColumnFilters(params: URLSearchParams, filters: ColumnFilters, columnIds: readonly string[]): void {
  for (const id of columnIds) {
    for (const value of sortValues(filters[id] ?? [])) params.append(`${PARAM_PREFIX}${id}`, value);
  }
}

/** A filter in a few words, for a chip: up to two values by name, else how many. */
export function describeFilter(values: readonly string[]): string {
  const named = values.map((v) => (v === "" ? BLANK_LABEL : v));
  return named.length <= 2 ? named.join(", ") : `${named.length} values`;
}
