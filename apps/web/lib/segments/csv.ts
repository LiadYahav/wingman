/**
 * The exports of what the Segments table shows: its rows, in its order, its
 * visible columns with the original's headers, as one table that the CSV
 * (`lib/table/csv.ts`) and the Excel file both write.
 */

import { toCsv } from "@/lib/table/csv";
import type { ExportTable } from "@/lib/table/export";
import type { Segment } from "@/types/segments";
import { COLUMN_LABELS, cellText, type ColumnId } from "./columns";

/** The shown segments in the shown columns: each cell's text, a VLAN ID as a number. */
export function segmentsTable(segments: Segment[], columns: ColumnId[]): ExportTable {
  return {
    header: columns.map((column) => COLUMN_LABELS[column]),
    rows: segments.map((segment) =>
      columns.map((column) => (column === "vlan_id" && segment.vlan_id !== null ? segment.vlan_id : cellText(segment, column)))
    ),
  };
}

/** The shown segments as CSV, in the shown columns. */
export function segmentsCsv(segments: Segment[], columns: ColumnId[]): string {
  const table = segmentsTable(segments, columns);
  return toCsv(table.header, table.rows.map((row) => row.map(String)));
}
