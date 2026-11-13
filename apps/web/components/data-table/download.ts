/**
 * Hand the browser a CSV to save. A byte-order mark leads the text so Excel
 * reads it as UTF-8.
 */
export function downloadCsv(filename: string, csv: string): void {
  const url = URL.createObjectURL(new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }));
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
