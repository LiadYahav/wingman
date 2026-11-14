/**
 * server-scan's `NetworkTab.test.tsx` and `ConnectivityTab.test.tsx` cases at
 * 92146d3 (decision 18), on the pure rules the tabs render.
 */

import { describe, expect, it } from "vitest";
import type { ConnectivityAttachment } from "@/types/server-scan-record";
import { attachmentDetails, bmcAddress, describeLocation, fabricGroups, interconnectName, speedText } from "./network";

function attachment(overrides: Partial<ConnectivityAttachment> = {}): ConnectivityAttachment {
  return {
    type: "FABRIC_INTERCONNECT", provider: "UCS_MANAGER", fabric: "A", fabric_name: "FI-A-TLV-01", fabric_id: "fi-01",
    fabric_model: "UCS-FI-6454", fabric_serial: "FCH123", server_interface: "vic1", server_port: "1",
    fabric_port: "Ethernet1/17", admin_state: "ENABLED", oper_state: "UP", speed_mbps: 25000,
    last_seen: "2026-08-12T10:00:00Z", interface_kind: "PHYSICAL", ...overrides,
  };
}

describe("a NIC's place", () => {
  it("reads an FQDD's location in words, distinguishing onboard from a slot", () => {
    expect(describeLocation({ name: "NIC.Integrated.1-1-1", location: "1/1/1" })).toBe("Onboard · port 1");
    expect(describeLocation({ name: "NIC.Slot.8-1-1", location: "8/1/1" })).toBe("Slot 8 · port 1");
  });
  it("keeps the BMC's location for anything else, and null when there is none", () => {
    expect(describeLocation({ name: "eth0", location: "Port 1" })).toBe("Port 1");
    expect(describeLocation({ name: "eth0", location: null })).toBeNull();
  });
  it("dashes a speed that was not read", () => {
    expect(speedText(25000)).toBe("25000 Mbps");
    expect(speedText(null)).toBe("—");
  });
});

describe("the BMC's address", () => {
  const bmc = { address_raw: "https://10.0.0.5:443/redfish", scheme: "https", host: "10.0.0.5", port: 443, mac: null };
  it("prefers the host over the raw address when both were read", () => {
    expect(bmcAddress(bmc)).toBe("10.0.0.5");
    expect(bmcAddress({ ...bmc, host: null })).toBe("https://10.0.0.5:443/redfish");
    expect(bmcAddress({ ...bmc, host: null, address_raw: null })).toBeNull();
  });
});

describe("fabric uplinks", () => {
  it("are none for zero attachments", () => {
    expect(fabricGroups([])).toEqual([]);
  });
  it("are one group for a single attachment, two for a dual-fabric pair", () => {
    expect(fabricGroups([attachment()]).map((g) => g.fabric)).toEqual(["A"]);
    expect(fabricGroups([attachment(), attachment({ fabric: "B", fabric_name: "FI-B" })]).map((g) => g.fabric)).toEqual(["A", "B"]);
  });
  it("group four attachments across three fabrics (A/A/B/C) in first-seen order", () => {
    const groups = fabricGroups([attachment(), attachment({ server_port: "2" }), attachment({ fabric: "B" }), attachment({ fabric: "C" })]);
    expect(groups.map((g) => [g.fabric, g.attachments.length])).toEqual([["A", 2], ["B", 1], ["C", 1]]);
  });
  it("put attachments with no fabric in a trailing Other", () => {
    expect(fabricGroups([attachment({ fabric: null }), attachment()]).map((g) => g.fabric)).toEqual(["A", null]);
  });
  it("show only the physical uplink, not the vNICs riding the same fabric; none with only vNICs", () => {
    const groups = fabricGroups([attachment(), attachment({ interface_kind: "VNIC", server_interface: "eth0" })]);
    expect(groups[0].attachments).toHaveLength(1);
    expect(fabricGroups([attachment({ interface_kind: "VNIC" })])).toEqual([]);
  });
  it("list an uplink's details as read, and name the interconnect", () => {
    expect(attachmentDetails(attachment({ fabric_serial: null, speed_mbps: null }))).toEqual([
      ["Model", "UCS-FI-6454"], ["Server interface", "vic1"], ["Server port", "1"], ["Fabric port", "Ethernet1/17"], ["Admin state", "ENABLED"],
    ]);
    expect(interconnectName(attachment({ fabric_name: null }))).toBe("fi-01");
    expect(interconnectName(attachment({ fabric_name: null, fabric_id: null }))).toBe("Unnamed interconnect");
  });
});
