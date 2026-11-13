/**
 * A table as CSV text: RFC 4180 quoting, CRLF line ends, and a cell that a
 * spreadsheet would read as a formula (`=`, `+`, `-`, `@`, a tab or CR first)
 * prefixed with `'` so it stays text. Shared by the tables' exports (the
 * Segments and Server Scan areas); `components/data-table/download.ts` saves it.
 */

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
