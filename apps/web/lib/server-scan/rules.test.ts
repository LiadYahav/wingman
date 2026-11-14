/**
 * server-scan's Rules & Policies page cases at 92146d3 (`RulesPage.test.tsx`;
 * decision 18), on the pure functions the page renders: the rules' scope and
 * pattern words, the policies' sections and their order, and a condition as
 * one line.
 */

import { describe, expect, it } from "vitest";
import type { HealthSeverity } from "@/types/server-scan";
import type { Condition, HealthPolicyResponse, PolicyScope } from "@/types/server-scan-rules";
import { conditionSummary, policyHint, policyScopeLabel, policyScopeRank, policySections, scopeSummary, severityRank } from "./rules";

const leaf = (metric: string, operator: string, value: unknown = null, equals: unknown = null): Condition => ({
  metric, operator, value, equals, all_of: null, any_of: null, not: null,
});
const node = (fields: Partial<Condition>): Condition => ({
  all_of: null, any_of: null, not: null, metric: null, operator: null, value: null, equals: null, ...fields,
});

function policy(id: string, name: string, severity: HealthSeverity, scope: PolicyScope): HealthPolicyResponse {
  return {
    id,
    name,
    description: "",
    enabled: true,
    system: true,
    policy_key: `storage.${id}`,
    mode: "EVALUATE",
    category: "storage",
    severity,
    condition: leaf("storage.failed_drive_count", "GTE", 1),
    evidence: [],
    message_template: "{bad} failed",
    scope,
    source: "SYSTEM_DEFAULT",
    priority: 100,
    order: 0,
    stats: { fire_count: 0, last_fired_at: null, error_count: 0, quarantined: false },
    revision: 1,
    created_at: "2026-09-01T06:00:00Z",
    updated_at: "2026-09-01T06:00:00Z",
    created_by: null,
    updated_by: null,
  };
}

const general = { vendor: null, manager_types: [], site_id: null };
// Deliberately out of section and severity order, as server-scan's test
const POLICIES = [
  policy("policy_1", "failed drive", "CRITICAL", { vendor: "dell", manager_types: [], site_id: null }),
  policy("policy_2", "general warning", "WARNING", general),
  policy("policy_3", "general critical", "CRITICAL", general),
  policy("policy_4", "general major", "MAJOR", general),
  policy("policy_5", "cisco vnic down", "MAJOR", { vendor: "cisco", manager_types: ["UCS_CENTRAL", "INTERSIGHT"], site_id: null }),
];

describe("the classification rules' words", () => {
  it("renders an unscoped rule as unscoped rather than blank", () => {
    expect(scopeSummary({ vendor: null, manager_type: null, site_id: null })).toBe("(unscoped)");
    expect(scopeSummary({ vendor: null, manager_type: null, site_id: "tlv" })).toBe("site=tlv");
    expect(scopeSummary({ vendor: "dell", manager_type: "OPENMANAGE", site_id: "tlv" })).toBe("vendor=dell, manager=OPENMANAGE, site=tlv");
  });
});

describe("the health policies' sections", () => {
  it("groups health policies by scope, General first, then vendor, then collector", () => {
    expect(policySections(POLICIES).map((s) => s.label)).toEqual(["General", "Dell", "Cisco — UCS Central, Intersight"]);
    expect(policySections(POLICIES).map((s) => s.rank)).toEqual([0, 1, 2]);
  });

  it("sorts each section by severity: CRITICAL, MAJOR, WARNING; then by name", () => {
    const [first] = policySections([...POLICIES, policy("policy_6", "another critical", "CRITICAL", general)]);
    expect(first?.policies.map((p) => p.name)).toEqual(["another critical", "general critical", "general major", "general warning"]);
  });

  it("a section heading names the vendor, then the collectors, then the site; a collector it does not know as it is", () => {
    expect(policyScopeLabel(general)).toBe("General");
    expect(policyScopeLabel({ vendor: "hp", manager_types: ["ONEVIEW"], site_id: "tlv" })).toBe("HPE — OneView — Site tlv");
    expect(policyScopeLabel({ vendor: null, manager_types: ["NEW_COLLECTOR"], site_id: null })).toBe("NEW_COLLECTOR");
    expect(policyScopeRank({ vendor: "dell", manager_types: ["OPENMANAGE"], site_id: "tlv" })).toBe(3);
  });

  it("an unknown severity sorts last", () => {
    expect(severityRank("CRITICAL")).toBe(0);
    expect(severityRank("UNKNOWN")).toBe(4);
    expect(severityRank("INFO" as HealthSeverity)).toBe(5);
  });
});

describe("a condition as one line", () => {
  it("renders a health policy's condition as readable text", () => {
    expect(conditionSummary(leaf("storage.failed_drive_count", "GTE", 1))).toBe("storage.failed_drive_count GTE 1");
  });

  it("AND, a bracketed OR, NOT, JSON values and a count's equals", () => {
    const psu = node({
      any_of: [leaf("power.failed_psu_count", "GTE", 2), node({ all_of: [leaf("power.failed_psu_count", "EQ", 1), leaf("power.psu_count", "LTE", 1)] })],
    });
    expect(conditionSummary(psu)).toBe("(power.failed_psu_count GTE 2 OR power.failed_psu_count EQ 1 AND power.psu_count LTE 1)");
    expect(conditionSummary(node({ not: leaf("raid.state", "EQ", "ABSENT") }))).toBe('NOT raid.state EQ "ABSENT"');
    expect(conditionSummary(leaf("server.name_has_10tb", "EQ", false))).toBe("server.name_has_10tb EQ false");
    expect(conditionSummary(leaf("storage.name_capacity_bytes", "EXISTS"))).toBe("storage.name_capacity_bytes EXISTS");
    expect(conditionSummary(leaf("gpu.states", "COUNT_GTE", 2, "DOWN"))).toBe('gpu.states COUNT_GTE 2 of "DOWN"');
    expect(conditionSummary(node({}))).toBe("—");
  });

  it("a policy's tooltip is its description and its message", () => {
    expect(policyHint({ ...POLICIES[0]!, description: "Fires on a failed drive." })).toBe("Fires on a failed drive.\nSays: {bad} failed");
    expect(policyHint(POLICIES[0]!)).toBe("Says: {bad} failed");
  });
});
