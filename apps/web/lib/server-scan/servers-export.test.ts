/**
 * The Servers export. The cases are server-scan's own
 * (`frontend/src/features/inventory/xlsxExport.test.ts` at 92146d3, decision
 * 18), asked of the table both files write instead of server-scan's zip; the
 * sheet's widths and bold header are the shared export's (`lib/table/export.test.ts`).
 */

import { describe, expect, it } from "vitest";
import { xlsxSheet } from "@/lib/table/export";
import { SHEET_NAME, exportName, serversCsv, serversTable } from "./servers-export";
import { serverRow as row } from "./testing";

describe("the Servers export", () => {
  it("writes the header row in the documented column order", () => {
    expect(serversTable([]).header).toEqual([
      "Name", "Vendor", "BMC address", "Model", "Serial", "SPT", "Installation", "MCE", "Cluster", "State",
    ]);
    expect(SHEET_NAME).toBe("Servers");
  });

  it("renders every field in order and leaves null cells empty", () => {
    const table = serversTable([
      row({
        name: "srv-a",
        bmc_host: "10.0.0.9",
        openshift_state: "INSTALLED",
        mce_name: "mce-1",
        cluster_name: "ocp4-tlv",
        model: "PowerEdge R760",
        serial: "SN001",
        profile_template_name: "gold-template",
        health: "CRITICAL",
      }),
      row({ name: "srv-b", bmc_host: null, mce_name: null, cluster_name: null }),
    ]);
    expect(table.rows[0]).toEqual([
      "srv-a", "dell", "10.0.0.9", "PowerEdge R760", "SN001", "gold-template", "INSTALLED", "mce-1", "ocp4-tlv", "CRITICAL",
    ]);
    expect(table.rows[1]).toEqual(["srv-b", "dell", "", "R760", "SN1", "", "AVAILABLE", "", "", "HEALTHY"]);
    // An empty cell is left empty in the Excel file
    expect(xlsxSheet(table).data[2]).toEqual(["srv-b", "dell", null, "R760", "SN1", null, "AVAILABLE", null, null, "HEALTHY"]);
  });

  it("caps a very long value instead of making a huge column", () => {
    expect(xlsxSheet(serversTable([row({ name: "x".repeat(300) })])).columns[0]).toEqual({ width: 50 });
  });

  it("keeps values that look like numbers or formulas as text", () => {
    const table = serversTable([row({ serial: "00123", bmc_host: "=1+1" })]);
    expect(table.rows[0]).toContain("00123");
    expect(table.rows[0]).toContain("=1+1");
    // The CSV keeps the formula as text for a spreadsheet too
    expect(serversCsv([row({ serial: "00123", bmc_host: "=1+1" })]).split("\r\n")[1]).toBe(
      "srv-1,dell,'=1+1,R760,00123,,AVAILABLE,,,HEALTHY"
    );
  });

  it("holds the rows given, in their order: the CSV and the Excel file hold the same", () => {
    const csv = serversCsv([row({ name: "b" }), row({ name: "a" })]);
    expect(csv.split("\r\n").map((line) => line.split(",")[0])).toEqual(["Name", "b", "a", ""]);
  });

  it("is named as server-scan names it, by the day", () => {
    const now = new Date("2026-11-13T22:15:00Z");
    expect(exportName(now, "xlsx")).toBe("inventory-2026-11-13.xlsx");
    expect(exportName(now, "csv")).toBe("inventory-2026-11-13.csv");
  });
});
