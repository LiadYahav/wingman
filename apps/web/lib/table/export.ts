/**
 * A table's rows as a file: one `ExportTable` (headers, then rows) that the
 * CSV and the Excel file both write, so they always hold the same rows and
 * columns. Pure; `components/data-table/download.ts` hands the file over.
 */

import type { Row, SheetData } from "write-excel-file/browser";

/** A cell: text, or a number Excel should keep as one (a VLAN ID). */
export type ExportCell = string | number;

export interface ExportTable {
  header: string[];
  rows: ExportCell[][];
}

/** The widest a column gets, in characters, as the original's export caps it. */
const MAX_WIDTH = 50;

/**
 * The Excel sheet for a table: the header row bold, each value as it is
 * (text stays text: a cell is never a formula), an empty cell left empty,
 * and each column as wide as its longest value plus 2, at most 50
 * characters (segments-manager's own export sizes its columns so).
 */
export function xlsxSheet(table: ExportTable): { data: SheetData; columns: { width: number }[] } {
  const header: Row = table.header.map((value) => ({ value, fontWeight: "bold" as const }));
  const rows: Row[] = table.rows.map((row) => row.map((value) => (value === "" ? null : value)));
  const columns = table.header.map((title, index) => {
    const longest = Math.max(title.length, ...table.rows.map((row) => String(row[index] ?? "").length));
    return { width: Math.min(longest + 2, MAX_WIDTH) };
  });
  return { data: [header, ...rows], columns };
}
