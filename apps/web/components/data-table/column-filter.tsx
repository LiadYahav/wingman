"use client";

import { useState } from "react";
import { Funnel, Search } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  BLANK_LABEL,
  describeFilter,
  distinctValues,
  filterOptions,
  setColumnFilter,
  type ColumnFilters,
} from "@/lib/table/column-filters";
import { cn } from "@/lib/utils";
import { CheckItem } from "./check-item";

/** The value filters a `DataTable` draws in the headers of the columns that opt in (`meta.filterValue`). */
export interface DataTableFilters<T> {
  /** The rows before any column filter: each popover lists its column's values from them. */
  rows: readonly T[];
  /** The values each column keeps (`lib/table/column-filters.ts`); the caller filters its rows with them. */
  value: ColumnFilters;
  onChange: (next: ColumnFilters) => void;
}

interface Props<T> {
  columnId: string;
  /** The column's header words: "Filter Type". */
  label: string;
  text: (row: T) => string;
  filters: DataTableFilters<T>;
}

const valueLabel = (value: string) => (value === "" ? BLANK_LABEL : value);

/**
 * A column's Excel-style filter: a funnel in its header, marked while the
 * column filters, opening the column's distinct values with checkboxes, a
 * search among them, select all or none, Apply and Clear (the original's
 * words: "Filter Type", "(Blank)", "No values").
 */
export function ColumnFilter<T>({ columnId, label, text, filters }: Props<T>) {
  const [open, setOpen] = useState(false);
  const kept = filters.value[columnId];
  const name = kept ? `Filter ${label} (filtered: ${describeFilter(kept)})` : `Filter ${label}`;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        aria-label={name}
        title={name}
        data-filtered={kept ? "true" : undefined}
        className={cn(
          "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded outline-none transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50",
          kept ? "text-primary" : "text-muted-foreground/50 hover:text-foreground"
        )}
      >
        <Funnel aria-hidden className={cn("h-3 w-3", kept && "fill-current")} />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 gap-0 p-0" aria-label={`Filter ${label}`} data-testid="column-filter">
        <FilterForm columnId={columnId} label={label} text={text} filters={filters} onDone={() => setOpen(false)} />
      </PopoverContent>
    </Popover>
  );
}

/** The popover's body: mounted on open, so it starts from the column's values and filter as they are then. */
function FilterForm<T>({ columnId, label, text, filters, onDone }: Props<T> & { onDone: () => void }) {
  const kept = filters.value[columnId];
  const [options] = useState(() => filterOptions(distinctValues(filters.rows, text), kept));
  const [draft, setDraft] = useState(() => new Set(kept ?? options));
  const [needle, setNeedle] = useState("");
  const query = needle.trim().toLowerCase();
  const visible = query ? options.filter((v) => valueLabel(v).toLowerCase().includes(query)) : options;
  const chosen = visible.filter((v) => draft.has(v)).length;
  const all = visible.length > 0 && chosen === visible.length;

  const toggle = (value: string) =>
    setDraft((current) => {
      const next = new Set(current);
      if (!next.delete(value)) next.add(value);
      return next;
    });
  const toggleAll = () =>
    setDraft((current) => {
      const next = new Set(current);
      for (const value of visible) {
        if (all) next.delete(value);
        else next.add(value);
      }
      return next;
    });
  const finish = (values: string[] | null) => {
    filters.onChange(setColumnFilter(filters.value, columnId, values, options));
    onDone();
  };

  return (
    <>
      <div className="relative border-b p-2">
        <Search aria-hidden className="pointer-events-none absolute left-4 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          aria-label={`Search ${label} values`}
          placeholder="Search…"
          value={needle}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => setNeedle(e.target.value)}
          className="w-full rounded-md border bg-card py-1 pl-7 pr-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 [&::-webkit-search-cancel-button]:hidden"
        />
      </div>
      <div className="p-1.5">
        <CheckItem checked={all ? true : chosen > 0 ? "mixed" : false} onToggle={toggleAll} disabled={visible.length === 0}>
          (Select all)
        </CheckItem>
        <div role="group" aria-label={`${label} values`} className="max-h-64 overflow-y-auto">
          {visible.length === 0 ? (
            <p className="px-2 py-1.5 text-sm text-muted-foreground">No values</p>
          ) : (
            visible.map((value) => (
              <CheckItem key={value} checked={draft.has(value)} onToggle={() => toggle(value)} className={cn(value === "" && "italic text-muted-foreground")}>
                <span title={valueLabel(value)}>{valueLabel(value)}</span>
              </CheckItem>
            ))
          )}
        </div>
      </div>
      <div className="flex items-center justify-end gap-2 border-t p-2">
        <button type="button" onClick={() => finish(null)} disabled={!kept} className={buttonVariants({ variant: "ghost", size: "sm" })}>
          Clear
        </button>
        <button type="button" onClick={() => finish([...draft])} disabled={draft.size === 0} className={buttonVariants({ size: "sm" })}>
          Apply
        </button>
      </div>
    </>
  );
}
