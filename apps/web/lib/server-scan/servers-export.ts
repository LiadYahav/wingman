/**
 * The Servers page's export: every row the filters keep, not only the page,
 * in the order shown, with server-scan's columns and headers
 * (team-redbull/server-scan at 92146d3, `frontend/src/features/inventory/xlsxExport.ts`,
 * decision 18). One `ExportTable` that the Excel file (Wingman's shared
 * `write-excel-file` export, in place of server-scan's own zip writer) and
 * the CSV both write, so they hold the same rows and columns. Every value
 * stays text: a serial with leading zeros or a leading `=` is never a number
 * or a formula.
 */

import { toCsv } from "@/lib/table/csv";
import type { ExportTable } from "@/lib/table/export";
import type { ServerRow } from "@/types/server-scan-servers";

/** server-scan's column order, header text and value. */
const COLUMNS: { header: string; value: (row: ServerRow) => string }[] = [
  { header: "Name", value: (r) => r.name },
  { header: "Vendor", value: (r) => r.vendor },
  { header: "BMC address", value: (r) => r.bmc_host ?? "" },
  { header: "Model", value: (r) => r.model ?? "" },
  { header: "Serial", value: (r) => r.serial ?? "" },
  { header: "SPT", value: (r) => r.profile_template_name ?? "" },
  { header: "Installation", value: (r) => r.openshift_state },
  { header: "MCE", value: (r) => r.mce_name ?? "" },
  { header: "Cluster", value: (r) => r.cluster_name ?? "" },
  { header: "State", value: (r) => r.health },
];

/** The sheet's name, as server-scan's. */
export const SHEET_NAME = "Servers";

/** The rows as the export's table, in the order given. */
export function serversTable(rows: readonly ServerRow[]): ExportTable {
  return {
    header: COLUMNS.map((c) => c.header),
    rows: rows.map((row) => COLUMNS.map((c) => c.value(row))),
  };
}

export function serversCsv(rows: readonly ServerRow[]): string {
  const table = serversTable(rows);
  return toCsv(table.header, table.rows.map((row) => row.map(String)));
}

/** server-scan's file name, `inventory-<YYYY-MM-DD>`, with the extension given. */
export function exportName(now: Date, extension: "xlsx" | "csv"): string {
  return `inventory-${now.toISOString().slice(0, 10)}.${extension}`;
}
