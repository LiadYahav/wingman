/**
 * The CSV of what the Segments table shows: its rows, in its order, its
 * visible columns with the original's headers. RFC 4180 quoting, CRLF line
 * ends, and a cell that a spreadsheet would read as a formula (`=`, `+`,
 * `-`, `@`, a tab or CR first) is prefixed with `'` so it stays text.
 */

import type { Segment } from "@/types/segments";
import { COLUMN_LABELS, cellText, type ColumnId } from "./columns";

const FORMULA_START = /^[=+\-@\t\r]/;
const NEEDS_QUOTES = /[",\r\n]/;

/** One cell, escaped. */
export function csvCell(value: string): string {
  const safe = FORMULA_START.test(value) ? `'${value}` : value;
  return NEEDS_QUOTES.test(safe) ? `"${safe.replaceAll('"', '""')}"` : safe;
}

/** A header row and the rows, as CSV text. */
export function toCsv(header: string[], rows: string[][]): string {
  return [header, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}

/** The shown segments as CSV, in the shown columns. */
export function segmentsCsv(segments: Segment[], columns: ColumnId[]): string {
  return toCsv(
    columns.map((column) => COLUMN_LABELS[column]),
    segments.map((segment) => columns.map((column) => cellText(segment, column)))
  );
}
