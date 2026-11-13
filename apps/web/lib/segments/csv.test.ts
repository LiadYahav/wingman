import { describe, expect, it } from "vitest";
import { COLUMN_IDS } from "./columns";
import { csvCell, segmentsCsv, segmentsTable, toCsv } from "./csv";
import { free, segment } from "./testing";

describe("a CSV cell", () => {
  it("is left alone when plain", () => {
    expect(csvCell("EPG_site1_HC_1408")).toBe("EPG_site1_HC_1408");
    expect(csvCell("")).toBe("");
  });

  it("is quoted for a comma, a quote or a line break, quotes doubled", () => {
    expect(csvCell("ocp4-upi-a, ocp4-upi-b")).toBe('"ocp4-upi-a, ocp4-upi-b"');
    expect(csvCell('say "hi"')).toBe('"say ""hi"""');
    expect(csvCell("two\nlines")).toBe('"two\nlines"');
  });

  it("stays text when a spreadsheet would run it as a formula", () => {
    expect(csvCell("=HYPERLINK(\"x\")")).toBe("\"'=HYPERLINK(\"\"x\"\")\"");
    expect(csvCell("+1")).toBe("'+1");
    expect(csvCell("-1")).toBe("'-1");
    expect(csvCell("@SUM(A1)")).toBe("'@SUM(A1)");
    expect(csvCell("\tx")).toBe("'\tx");
  });
});

describe("the CSV", () => {
  it("has the header, then one CRLF line per row", () => {
    expect(toCsv(["a", "b"], [["1", "2"], ["3", ""]])).toBe("a,b\r\n1,2\r\n3,\r\n");
    expect(toCsv(["a"], [])).toBe("a\r\n");
  });

  it("is the shown segments in the shown columns, with the original's headers", () => {
    const rows = [
      segment(),
      segment({ segment: "10.20.60.0/24", vlan_id: 1460, epg_name: "EPG_site1_UPI_1460", type: "UPI", dhcp: false, cluster_name: ["ocp4-upi-a", "ocp4-upi-b"] }),
      free({ segment: "10.20.48.0/24", vlan_id: 1414, epg_name: "EPG_site1_HC_1414", status: null, dhcp: null }),
    ];
    expect(segmentsCsv(rows, [...COLUMN_IDS])).toBe(
      [
        "Type,Site,VLAN ID,EPG Name,Network Segment,DHCP,Cluster,Status",
        "HC,site1,1408,EPG_site1_HC_1408,10.20.42.0/24,On,ocp4-prep-eyal-site1,Allocated",
        'UPI,site1,1460,EPG_site1_UPI_1460,10.20.60.0/24,Off,"ocp4-upi-a, ocp4-upi-b",Allocated',
        ",site1,1414,EPG_site1_HC_1414,10.20.48.0/24,,,Available",
        "",
      ].join("\r\n")
    );
    expect(segmentsCsv(rows.slice(0, 1), ["vlan_id", "segment"])).toBe("VLAN ID,Network Segment\r\n1408,10.20.42.0/24\r\n");
  });

  it("is the same table the Excel file writes, a VLAN ID kept as a number", () => {
    const rows = [segment(), free({ segment: "10.20.48.0/24", vlan_id: null, epg_name: null, dhcp: null })];
    const table = segmentsTable(rows, ["vlan_id", "segment", "dhcp", "status"]);
    expect(table).toEqual({
      header: ["VLAN ID", "Network Segment", "DHCP", "Status"],
      rows: [
        [1408, "10.20.42.0/24", "On", "Allocated"],
        ["", "10.20.48.0/24", "", "Available"],
      ],
    });
    expect(segmentsCsv(rows, ["vlan_id", "segment", "dhcp", "status"])).toBe(
      "VLAN ID,Network Segment,DHCP,Status\r\n1408,10.20.42.0/24,On,Allocated\r\n,10.20.48.0/24,,Available\r\n"
    );
  });
});
