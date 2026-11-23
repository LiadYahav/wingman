"use client";

import { getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";

/**
 * A TanStack table over rows the caller already ordered. One row id per
 * row, so React keeps a row across re-reads.
 */
export function useDataTable<T>({
  data,
  columns,
  getRowId,
}: {
  data: T[];
  columns: ColumnDef<T, never>[];
  getRowId: (row: T) => string;
}) {
  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Table v8's API; the table is rebuilt from props each render
  return useReactTable<T>({ data, columns, getRowId, getCoreRowModel: getCoreRowModel() });
}
