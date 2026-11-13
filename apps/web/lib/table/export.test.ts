import { describe, expect, it } from "vitest";
import { xlsxSheet } from "./export";

describe("the Excel sheet", () => {
  it("has the header bold, then the rows: numbers stay numbers, text stays text, an empty cell is empty", () => {
    const sheet = xlsxSheet({ header: ["VLAN ID", "EPG Name"], rows: [[1418, "=HYPERLINK(\"x\")"], [9, ""]] });
    expect(sheet.data).toEqual([
      [{ value: "VLAN ID", fontWeight: "bold" }, { value: "EPG Name", fontWeight: "bold" }],
      [1418, "=HYPERLINK(\"x\")"],
      [9, null],
    ]);
  });

  it("sizes each column to its longest value plus 2, at most 50, as segments-manager's export", () => {
    const long = "x".repeat(80);
    const sheet = xlsxSheet({ header: ["Site", "VLAN ID", "Cluster"], rows: [["site1", 1418, long], ["site-number-two", 9, "a"]] });
    expect(sheet.columns).toEqual([{ width: 17 }, { width: 9 }, { width: 50 }]);
  });

  it("still has a header with no rows", () => {
    expect(xlsxSheet({ header: ["Type"], rows: [] })).toEqual({ data: [[{ value: "Type", fontWeight: "bold" }]], columns: [{ width: 6 }] });
  });
});
