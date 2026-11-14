import { xlsxSheet, type ExportTable } from "@/lib/table/export";

/** Hand the browser a file to save under `filename`. */
export function saveBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoked a moment later: a browser may still be reading it when click() returns
  setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

/**
 * Hand the browser a CSV to save. A byte-order mark leads the text so Excel
 * reads it as UTF-8.
 */
export function downloadCsv(filename: string, csv: string): void {
  saveBlob(filename, new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }));
}

/**
 * Hand the browser an Excel file (`.xlsx`) of `table`, one sheet named
 * `sheet`, its header row bold and kept in view. Written here, in the
 * browser, by write-excel-file (pinned exactly, ADR-0003; ADR-0047's 3.21.0
 * amendment), which is loaded on the first export only, so no page carries
 * it until then.
 */
export async function downloadXlsx(filename: string, table: ExportTable, sheet: string): Promise<void> {
  const { default: writeXlsxFile } = await import("write-excel-file/browser");
  const { data, columns } = xlsxSheet(table);
  saveBlob(filename, await writeXlsxFile(data, { sheet, columns, stickyRowsCount: 1 }).toBlob());
}
