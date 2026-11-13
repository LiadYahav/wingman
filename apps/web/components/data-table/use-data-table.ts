"use client";

import { getCoreRowModel, useReactTable, type ColumnDef, type VisibilityState } from "@tanstack/react-table";

/**
 * A TanStack table over rows the caller already filtered and sorted (the
 * sort lives in the caller's state, often the URL), with the columns it may
 * hide. One row id per row, so React keeps a row across re-reads.
 */
export function useDataTable<T>({
  data,
  columns,
  getRowId,
  columnVisibility,
  onColumnVisibilityChange,
}: {
  data: T[];
  columns: ColumnDef<T, never>[];
  getRowId: (row: T) => string;
  columnVisibility: VisibilityState;
  onColumnVisibilityChange: (next: VisibilityState) => void;
}) {
  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Table v8's API; the table is rebuilt from props each render
  return useReactTable<T>({
    data,
    columns,
    getRowId,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    state: { columnVisibility },
    onColumnVisibilityChange: (updater) =>
      onColumnVisibilityChange(typeof updater === "function" ? updater(columnVisibility) : updater),
  });
}
