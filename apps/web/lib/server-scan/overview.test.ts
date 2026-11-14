/**
 * server-scan's `OverviewTab.test.tsx` and `ReservationBadge.test.tsx` cases
 * at 92146d3 (decision 18), on the rules the Overview tab renders.
 */

import { describe, expect, it } from "vitest";
import {
  categoryLabel, collectionText, healthCategories, maintenanceText, maintenanceWhen, matchedRuleText, profileTemplateLabel,
  raidNote, reservationDetail,
} from "./overview";
import { gpu, serverRecord } from "./testing";

const labels = (record: ReturnType<typeof serverRecord>) => healthCategories(record).map((c) => c.label);

describe("the health breakdown", () => {
  it("shows a UCS server's checks, no GPU row without GPUs, no Name row until it is judged", () => {
    expect(labels(serverRecord())).toEqual(["Memory", "Storage", "RAID", "Network", "Connectivity", "Power"]);
  });

  it("shows the Name badge only when there is something to compare", () => {
    const record = serverRecord();
    expect(labels({ ...record, health: { ...record.health, name: "HEALTHY" } })).toContain("Name");
  });

  it("shows the GPU row on a server with GPUs", () => {
    const record = serverRecord();
    expect(labels({ ...record, hardware: { ...record.hardware, gpus: [gpu()] } })).toContain("GPU");
  });

  it("shows no BMC, RAID, Connectivity or Power row for a KubeVirt VM, which has none of them", () => {
    expect(labels(serverRecord({ source_provider: "KUBEVIRT" }))).toEqual(["Memory", "Storage", "Network"]);
  });

  it("keeps the BMC and RAID rows for a Dell server, where the check ran; no Connectivity", () => {
    expect(labels(serverRecord({ source_provider: "OPENMANAGE" }))).toEqual(["Memory", "Storage", "RAID", "Network", "Power", "BMC"]);
  });

  it("carries each category's severity, and names a reason's category in its words", () => {
    const record = serverRecord();
    const storage = healthCategories({ ...record, health: { ...record.health, storage: "CRITICAL" } }).find((c) => c.key === "storage");
    expect(storage?.severity).toBe("CRITICAL");
    expect(categoryLabel("storage")).toBe("Storage");
    expect(categoryLabel("thermal")).toBe("thermal");
  });

  it("says which BMC and method answered RAID, and why it is Unknown", () => {
    expect(raidNote({ state: "PRESENT", method: "redfish_storage", bmc: "iDRAC9", reason: null })).toBe("iDRAC9 · redfish_storage");
    expect(raidNote({ state: "UNKNOWN", method: null, bmc: null, reason: "the BMC cannot report RAID" })).toBe("the BMC cannot report RAID");
    expect(raidNote({ state: "ABSENT", method: null, bmc: null, reason: "x" })).toBeNull();
    expect(raidNote(null)).toBeNull();
  });
});

describe("the profile template, in the collector's own vendor terms", () => {
  it.each([
    ["UCS_CENTRAL", "Service profile template"],
    ["INTERSIGHT", "Server profile template"],
    ["ONEVIEW", "Server profile template"],
    ["OPENMANAGE", "Deployment template"],
  ])("%s: %s", (provider, label) => {
    expect(profileTemplateLabel(provider)).toBe(label);
  });

  it("omits the row for a standalone BMC, a VM, and a server with no source provider", () => {
    expect(profileTemplateLabel("REDFISH_STANDALONE")).toBeNull();
    expect(profileTemplateLabel("KUBEVIRT")).toBeNull();
    expect(profileTemplateLabel(null)).toBeNull();
  });
});

describe("a BMC the collector could not read", () => {
  it("says why and since when", () => {
    expect(collectionText("not_an_idrac", null)).toBe("Not an iDRAC");
    expect(collectionText("auth_rejected", "2026-08-13T10:00:00Z")).toMatch(/^Wrong credentials since 13\/08\/2026, 13:00:00/);
    expect(collectionText(null, "2026-08-13T10:00:00Z")).toMatch(/^Unreachable since/);
  });
});

describe("the matched rule", () => {
  const rule = { installation_type: "UPI" as const, matched_rule_id: "r1", matched_rule_name: "UPI workers", matched_field: "name", matched_pattern: "^upi-" };
  it("names the rule and what it matched on", () => {
    expect(matchedRuleText(rule)).toBe("UPI workers (name ~ ^upi-)");
    expect(matchedRuleText({ ...rule, matched_pattern: null })).toBe("UPI workers");
  });
  it("shows nothing for a legacy classification", () => {
    expect(matchedRuleText({ ...rule, matched_rule_name: null })).toBeNull();
  });
});

describe("an install lock's details", () => {
  const lock = { held: true, holder: "add-server-to-mce", mce_cluster: "mce-a", infra_env: "dell-r760", expires_at: "2026-11-13T16:00:00Z" };
  it("says where, which InfraEnv, by whom and until when", () => {
    expect(reservationDetail(lock)).toBe("Installing to mce-a · InfraEnv dell-r760 · held by add-server-to-mce · lock expires 13/11/2026, 18:00:00 GMT+2");
  });
  it("names an unnamed MCE and a lock with no expiry", () => {
    expect(reservationDetail({ ...lock, mce_cluster: null, infra_env: null, holder: null, expires_at: null })).toBe(
      "Installing to an unnamed MCE · lock has no expiry"
    );
  });
});

describe("a maintenance in words", () => {
  const m = { enabled: true, reason: "fan swap", created_by: "api-token-admin", created_at: "2026-11-12T09:00:00Z", updated_at: null, expected_end: null };
  it("is the reason and who, a token by its name", () => {
    expect(maintenanceText(m)).toBe("fan swap - by API token (admin)");
    expect(maintenanceText({ ...m, reason: null, created_by: null })).toBe("Enabled");
    expect(maintenanceText({ ...m, enabled: false })).toBeNull();
  });
  it("says since when and until when, in its tooltip", () => {
    expect(maintenanceWhen(m)).toMatch(/^Since 12\/11\/2026, 11:00:00/);
    expect(maintenanceWhen({ ...m, expected_end: "2026-11-14T14:00:00Z" })).toMatch(/expected to end 14\/11\/2026, 16:00:00/);
    expect(maintenanceWhen({ ...m, created_at: null })).toBeNull();
  });
});
