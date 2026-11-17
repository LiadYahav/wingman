import { describe, expect, it } from "vitest";
import { COLUMN_IDS } from "./columns";
import { segmentsCsv, segmentsTable } from "./csv";
import { free, segment } from "./testing";

describe("the CSV", () => {
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
