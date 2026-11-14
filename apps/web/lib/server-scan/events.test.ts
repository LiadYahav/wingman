/**
 * server-scan's `describeEvent.test.ts`, `EventTimeline.test.tsx` and
 * `EventList` cases at 92146d3 (decision 18), on the pure functions the
 * History tab renders.
 */

import { describe, expect, it } from "vitest";
import type { AuditEvent, AuditEventPage } from "@/types/server-scan-record";
import {
  WRITTEN_EVENT_TYPES, describeEvent, eventTone, healthSections, eventPager, matchedRule, topReason, transition, transitionSides, visibleData,
} from "./events";
import { auditEvent as ev } from "./testing";

describe("an event in a sentence", () => {
  it.each([
    ["SERVER_CREATED", { vendor: "dell", name: "x" }, "Server discovered"],
    ["SERVER_RENAMED", { name_from: "ocp-a-5tb", name_to: "ocp-a-10tb" }, "Renamed ocp-a-5tb → ocp-a-10tb"],
    ["SERVER_PRUNED", { reason: "r" }, "Pruned: no longer listed by its manager"],
    ["AUDIT_PURGED", { deleted: 1200, retention_days: 180 }, "Purged 1200 audit events older than 180 days"],
    ["HEALTH_CHANGED", { from: "HEALTHY", to: "CRITICAL" }, "HEALTHY → CRITICAL"],
    ["CLASSIFICATION_CHANGED", { from: "UPI", to: "HOSTED" }, "Classification UPI -> HOSTED"],
    [
      "CLASSIFICATION_CHANGED",
      { from: "UNCLASSIFIED", to: "UPI", name_from: "srv-1", name_to: "ocp4-1" },
      "Classification UNCLASSIFIED -> UPI (renamed srv-1 -> ocp4-1)",
    ],
    ["IDRAC_RESET", { trigger: "both", outcome: "requested" }, "iDRAC restart requested: every disk and every NIC UNKNOWN"],
    [
      "IDRAC_RESET",
      { trigger: "nics", outcome: "requested", power_state: "On", powered_on: false },
      "Host was already on: only the iDRAC restart requested: every NIC UNKNOWN",
    ],
    [
      "IDRAC_RESET",
      { trigger: "nics", outcome: "requested", power_state: "Off", powered_on: true },
      "Host was off: powered on, then iDRAC restart requested: every NIC UNKNOWN",
    ],
    [
      "IDRAC_RESET",
      { trigger: "nics", outcome: "failed", power_state: "Off", powered_on: true, detail: "the host did not report On within 120s of the power-on" },
      "Host was off: power-on sent, iDRAC not restarted (the host did not report On within 120s of the power-on): every NIC UNKNOWN",
    ],
    ["IDRAC_RESET", { trigger: "nics", outcome: "unconfirmed" }, "iDRAC restart sent, no reply (the iDRAC dropped the connection): every NIC UNKNOWN"],
    ["IDRAC_RESET", { trigger: "disks", outcome: "failed", detail: "403" }, "iDRAC restart failed (403): every disk UNKNOWN"],
    ["OPENSHIFT_STATE_CHANGED", { from: "AVAILABLE", to: "INSTALLED", cluster_name: "ocp4-tlv" }, "OpenShift state AVAILABLE -> INSTALLED (ocp4-tlv)"],
    ["MAINTENANCE_ENABLED", { reason: "fan swap" }, "Put into maintenance by System (sys): fan swap"],
    ["MAINTENANCE_ENABLED", { reason: "Donor for x" }, "Marked as parts donor by System (sys): Donor for x"],
    ["MAINTENANCE_ENABLED", { reason: null }, "Put into maintenance by System (sys)"],
    ["MAINTENANCE_ENABLED", { reason: "legacy", ticket: "T-1" }, "Put into maintenance by System (sys): legacy"],
    ["MAINTENANCE_UPDATED", { reason: "longer" }, "Updated maintenance by System (sys): longer"],
    ["MAINTENANCE_DISABLED", {}, "Maintenance ended"],
    ["SERVER_RESERVED", { holder: "wf", mce_cluster: "mce1", infra_env: "i", workflow_id: "w", expires_at: "x" }, "Reserved by wf for mce1"],
    ["SERVER_RESERVATION_REFUSED", { requested_by: "a", held_by: "b", held_for_mce: "m" }, "Reservation by a refused: held by b"],
    ["SERVER_RESERVATION_REFUSED", { requested_by: "a", reason: "lost the revision race" }, "Reservation by a refused: lost the revision race"],
    ["SERVER_RELEASED", { holder: "wf", mce_cluster: "mce1", workflow_id: "w" }, "Released from wf (mce1)"],
    ["SOMETHING_NEW", {}, "SOMETHING_NEW"],
  ])("%s %j", (type, data, expected) => {
    expect(describeEvent(ev(type, data))).toBe(expected);
  });

  it("puts the actor into maintenance sentences", () => {
    const by = (actor: AuditEvent["actor"], reason: string) => describeEvent({ ...ev("MAINTENANCE_ENABLED", { reason }), actor });
    expect(by({ type: "USER", id: "alice", display: null }, "fan swap")).toBe("Put into maintenance by alice: fan swap");
    expect(by({ type: "TOKEN", id: "api-token-admin", display: null }, "fan swap")).toBe("Put into maintenance by API token (admin): fan swap");
    expect(by({ type: "USER", id: "alice", display: "Alice" }, "donor")).toBe("Marked as parts donor by Alice: donor");
  });

  it("says who logged in with which role, and that a refused login had no permission", () => {
    expect(describeEvent(ev("LOGIN_SUCCEEDED", { role: "AUDITOR" }))).toBe("Logged in as auditor");
    expect(describeEvent(ev("LOGIN_DENIED", { role: "NO_PERMISSION" }))).toBe("Login refused: authenticated, but in no admin, auditor or viewer list");
  });

  it("describes creating and revoking a personal token, and a job run by hand", () => {
    expect(describeEvent(ev("TOKEN_CREATED", { role: "AUDITOR", expires_at: "2027-01-30T10:00:00+00:00" }))).toBe(
      "Created a personal API token (auditor, expires 2027-01-30)"
    );
    expect(describeEvent(ev("TOKEN_REVOKED", { user: "dana", by_admin: true }))).toBe("Personal API token of dana revoked by an admin");
    expect(describeEvent(ev("JOB_TRIGGERED", { cronjob: "r-collector-oneview", job: "r-collector-oneview-manual-ab12cd" }))).toBe(
      "Ran CronJob r-collector-oneview by hand as Job r-collector-oneview-manual-ab12cd"
    );
  });

  it("covers every written type", () => {
    for (const t of WRITTEN_EVENT_TYPES) expect(describeEvent(ev(t))).not.toBe(t);
  });
});

describe("a health change's reasons", () => {
  const base = { from: "MAJOR", to: "CRITICAL" };
  const reason = (name: string, severity: string, message = "x") => ({ policy_key: name, policy_name: name, category: "storage", severity, message });

  it("describes only the transition; the reasons are their own sections", () => {
    const d = { ...base, to_reasons: [reason("A", "CRITICAL"), reason("B", "CRITICAL")] };
    expect(describeEvent(ev("HEALTH_CHANGED", d))).toBe("MAJOR → CRITICAL");
    expect(healthSections(d).to).toHaveLength(2);
    expect(healthSections(d).from).toBeNull();
  });

  it("reads both sides, falls back to legacy reasons, and has none otherwise", () => {
    const both = healthSections({ from_reasons: [reason("A", "MAJOR")], to_reasons: [] });
    expect(both.from).toHaveLength(1);
    expect(both.to).toEqual([]);
    expect(healthSections({ reasons: [reason("A", "MAJOR")] }).to).toHaveLength(1);
    expect(healthSections(base)).toEqual({ from: null, to: null });
  });

  it("keeps only the most severe reason per side, the first one on a tie", () => {
    const reasons = healthSections({ to_reasons: [reason("warn", "WARNING"), reason("crit1", "CRITICAL"), reason("crit2", "CRITICAL")] }).to ?? [];
    expect(topReason(reasons)?.policy_key).toBe("crit1");
    expect(topReason([])).toBeNull();
  });

  it("dashes a missing value: the reason's fields are null, not absent", () => {
    const [r] = healthSections({ to_reasons: [{ policy_key: "k", severity: "MAJOR" }] }).to ?? [];
    expect(r).toEqual({ policy_key: "k", policy_name: null, category: null, severity: "MAJOR", message: null });
  });
});

describe("a status change's sides", () => {
  it("are FROM → TO, with ? for a missing side; none for an event without a transition", () => {
    expect(transition({ from: "UPI" })).toBe("UPI → ?");
    expect(transitionSides({ from: "AVAILABLE", to: "INSTALLED" })).toEqual(["AVAILABLE", "INSTALLED"]);
    expect(transitionSides({ reason: "x" })).toBeNull();
  });
});

describe("the details", () => {
  it("hide the legacy ticket and matched_rule_id keys without touching the event", () => {
    const e = ev("CLASSIFICATION_CHANGED", { to: "UPI", ticket: "T", matched_rule_id: "r" });
    expect(visibleData(e)).toEqual({ to: "UPI" });
    expect(e.data).toHaveProperty("ticket");
  });

  it("show the rule name and what it matched on; nothing for a legacy event with only a rule id", () => {
    expect(matchedRule({ matched_rule: "UPI workers", matched_field: "name", matched_pattern: "^upi-" })).toEqual({ name: "UPI workers", on: "name ~ ^upi-" });
    expect(matchedRule({ matched_rule: "UPI workers" })).toEqual({ name: "UPI workers", on: null });
    expect(matchedRule({ matched_rule_id: "r1" })).toBeNull();
  });
});

describe("an event type's tint", () => {
  it.each([
    ["HEALTH_CHANGED", "warning"],
    ["MAINTENANCE_ENABLED", "maintenance"],
    ["SERVER_RESERVATION_REFUSED", "critical"],
    ["SERVER_RESERVED", "info"],
    ["LOGIN_DENIED", "critical"],
    ["LOGIN_SUCCEEDED", "info"],
    ["CLASSIFICATION_CHANGED", "major"],
    ["SERVER_CREATED", "healthy"],
    ["SOMETHING_NEW", "neutral"],
  ])("%s is %s", (type, tone) => {
    expect(eventTone(type)).toBe(tone);
  });
});

describe("the pager", () => {
  const page = (total: number | null, hasMore: boolean): AuditEventPage => ({
    items: [], page: { next_cursor: hasMore ? "c" : null, has_more: hasMore, page_size: 50, total },
  });
  it("counts the pages from the first page's total", () => {
    expect(eventPager([page(132, true)], 0, true)).toEqual({ pageCount: 3, canNext: true });
    expect(eventPager([page(10, false)], 0, false)).toEqual({ pageCount: 1, canNext: false });
  });
  it("without a total, counts the pages read and one more while there are more", () => {
    expect(eventPager([page(null, true), page(null, true)], 1, true)).toEqual({ pageCount: 3, canNext: true });
    expect(eventPager([page(null, true), page(null, false)], 0, false)).toEqual({ pageCount: 2, canNext: true });
  });
});
