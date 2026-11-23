"use client";

import type { HTMLAttributes, ReactNode } from "react";
import { flexRender, type RowData, type Table } from "@tanstack/react-table";
import { cn } from "@/lib/utils";

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- the names must match TanStack's declaration
  interface ColumnMeta<TData extends RowData, TValue> {
    /** Classes for the column's header and cells (width, alignment). */
    className?: string;
  }
}

/**
 * The lines between rows, and the firmer one under the header, from the
 * foreground so they show in both themes (1.4-1.5:1 and 1.5-1.8:1, about
 * Apple's separators; the theme's `border` at 60% was 1.15:1), and 3:1 or
 * more when the system asks for more contrast.
 */
const DIVIDER = {
  rows: "divide-foreground/15 contrast-more:divide-foreground/50",
  header: "border-foreground/20 contrast-more:border-foreground/55",
};

/**
 * Wingman's one data table, on TanStack Table: dense rows and a sticky
 * header. The caller owns the rows' order; the table renders what it is
 * given.
 */
export function DataTable<T>({
  table,
  label,
  rowProps,
  empty,
  className,
}: {
  table: Table<T>;
  /** The table's accessible name. */
  label: string;
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
        <thead className="sticky top-0 z-10 bg-muted/90 backdrop-blur supports-[backdrop-filter]:bg-muted/75">
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id} className={cn("border-b", DIVIDER.header)}>
              {group.headers.map((header) => (
                <th
                  key={header.id}
                  scope="col"
                  data-column={header.column.id}
                  className={cn(
                    "whitespace-nowrap px-3 py-2 text-left text-xs font-semibold tracking-[0.01em] text-foreground/75",
                    header.column.columnDef.meta?.className
                  )}
                >
                  {flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody className={cn("divide-y", DIVIDER.rows)}>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns}>{empty}</td>
            </tr>
          ) : (
            rows.map((row) => {
              const { className: rowClassName, ...extra } = rowProps?.(row.original) ?? {};
              return (
                <tr key={row.id} className={cn("transition-colors hover:bg-muted/40", rowClassName)} {...extra}>
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
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
