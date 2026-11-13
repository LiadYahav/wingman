"use client";

import type { HTMLAttributes, ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { flexRender, type RowData, type Table } from "@tanstack/react-table";
import { cn } from "@/lib/utils";

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- the names must match TanStack's declaration
  interface ColumnMeta<TData extends RowData, TValue> {
    /** The header's words; the column picker lists them. */
    label: string;
    /** Classes for the column's header and cells (width, alignment). */
    className?: string;
  }
}

export interface DataTableSort {
  id: string;
  desc: boolean;
}

/**
 * Wingman's one data table, on TanStack Table (ADR-0047): dense rows, sticky
 * headers, every column sortable by a header button, columns hidden through
 * the table's visibility state (`ColumnPicker`). The caller owns the rows'
 * order and filtering (pure functions, unit-tested) and the sort state, so
 * the state can live in the URL; the table renders what it is given.
 *
 * Per-column filters can be added later the TanStack way: `columnFilters`
 * state and `getFilteredRowModel()` in `useDataTable`, with a control in the
 * header through the column's `meta`.
 */
export function DataTable<T>({
  table,
  label,
  sort,
  onSort,
  rowProps,
  empty,
  className,
}: {
  table: Table<T>;
  /** The table's accessible name. */
  label: string;
  sort: DataTableSort | null;
  /** A header was pressed: the caller decides the next sort (asc, desc, off). */
  onSort?: (columnId: string) => void;
  /** Extra attributes for a row: test ids, a tint. */
  rowProps?: (row: T) => HTMLAttributes<HTMLTableRowElement> & Record<`data-${string}`, string | undefined>;
  /** Shown in place of the rows when there are none. */
  empty?: ReactNode;
  className?: string;
}) {
  const rows = table.getRowModel().rows;
  const columns = table.getVisibleLeafColumns().length;
  return (
    <div className={cn("overflow-auto rounded-xl border bg-card", className)}>
      <table aria-label={label} className="w-full border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-muted/60 backdrop-blur supports-[backdrop-filter]:bg-muted/40">
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id} className="border-b">
              {group.headers.map((header) => {
                const meta = header.column.columnDef.meta;
                const sorted = sort?.id === header.column.id ? (sort.desc ? "descending" : "ascending") : undefined;
                const SortIcon = sorted === "ascending" ? ArrowUp : sorted === "descending" ? ArrowDown : ChevronsUpDown;
                return (
                  <th
                    key={header.id}
                    scope="col"
                    aria-sort={sorted}
                    data-column={header.column.id}
                    className={cn("whitespace-nowrap px-3 py-2 text-left text-xs font-medium text-muted-foreground", meta?.className)}
                  >
                    {onSort ? (
                      <button
                        type="button"
                        onClick={() => onSort(header.column.id)}
                        className="group inline-flex items-center gap-1 rounded outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        <SortIcon
                          aria-hidden
                          className={cn("h-3 w-3 shrink-0", sorted ? "text-foreground" : "opacity-0 group-hover:opacity-60 group-focus-visible:opacity-60")}
                        />
                      </button>
                    ) : (
                      flexRender(header.column.columnDef.header, header.getContext())
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody className="divide-y divide-border/60">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns}>{empty}</td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={row.id} className="transition-colors hover:bg-muted/40" {...rowProps?.(row.original)}>
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    data-column={cell.column.id}
                    className={cn("px-3 py-1.5 align-middle", cell.column.columnDef.meta?.className)}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
