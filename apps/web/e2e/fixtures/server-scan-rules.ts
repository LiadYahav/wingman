/**
 * The Rules & Policies page's mocks (docs/notes/2026-11-13-server-scan-area-api.md
 * §13), typed so a shape change fails `tsc`: made-up classification rules
 * and health policies in server-scan's own shapes, every condition node with
 * every field (the unused ones null), the policies deliberately out of
 * section and severity order, as server-scan's own test has them.
 */

import type { Page, Route } from "@playwright/test";
import { json } from "./api-handlers";
import { setUpServerScan } from "./server-scan";
import type { HealthSeverity } from "../../types/server-scan";
import type {
  ClassificationRuleListResponse, ClassificationRuleResponse, Condition, HealthPolicyListResponse, HealthPolicyResponse, PolicyScope,
} from "../../types/server-scan-rules";

const AT = "2026-09-01T06:00:00Z";

const node = (fields: Partial<Condition>): Condition => ({
  all_of: null, any_of: null, not: null, metric: null, operator: null, value: null, equals: null, ...fields,
});
const leaf = (metric: string, operator: string, value: unknown = null) => node({ metric, operator, value });

function rule(overrides: Partial<ClassificationRuleResponse>): ClassificationRuleResponse {
  return {
    id: "rule-hc",
    name: "Hosted cluster nodes",
    description: "Hosted-cluster nodes, named after their hardware spec and site.",
    enabled: true,
    system: true,
    installation_type: "HOSTED_CLUSTER",
    scope: { vendor: null, manager_type: null, site_id: null },
    field: "name",
    pattern: "^ocp-[a-z]+-[a-z0-9]+-site",
    flags: { ignore_case: true, multiline: false, dotall: false },
    source: "SYSTEM_DEFAULT",
    priority: 100,
    order: 0,
    stats: { last_matched_at: null, timeout_count: 0, quarantined: false },
    revision: 1,
    created_at: AT,
    updated_at: AT,
    created_by: null,
    updated_by: null,
    ...overrides,
  };
}

/** In server-scan's order: highest priority first, then its order. */
export const RULES: ClassificationRuleListResponse = {
  items: [
    rule({
      id: "rule-lab",
      name: "Lab nodes in Tel Aviv",
      description: "",
      pattern: "^lab-",
      scope: { vendor: "dell", manager_type: "OPENMANAGE", site_id: "tlv" },
      source: "SITE_CUSTOM",
      priority: 500,
      flags: { ignore_case: false, multiline: false, dotall: false },
    }),
    rule({}),
    rule({ id: "rule-mce", name: "MCE nodes", description: "An MCE hub's own nodes.", installation_type: "MCE", pattern: "^mce-", order: 1 }),
    rule({ id: "rule-upi", name: "UPI nodes", description: "", installation_type: "UPI", pattern: "^upi-", order: 2 }),
  ],
};

function policy(id: string, name: string, severity: HealthSeverity, scope: Partial<PolicyScope>, condition: Condition): HealthPolicyResponse {
  return {
    id,
    name,
    description: `${name}: why it fires.`,
    enabled: true,
    system: true,
    policy_key: `key.${id}`,
    mode: "EVALUATE",
    category: "storage",
    severity,
    condition,
    evidence: [],
    message_template: "{bad} of {total} failed",
    scope: { site_id: null, vendor: null, manager_types: [], ...scope },
    source: "SYSTEM_DEFAULT",
    priority: 100,
    order: 0,
    stats: { fire_count: 0, last_fired_at: null, error_count: 0, quarantined: false },
    revision: 1,
    created_at: AT,
    updated_at: AT,
    created_by: null,
    updated_by: null,
  };
}

const FAILED_DRIVE = leaf("storage.failed_drive_count", "GTE", 1);

// Deliberately out of section and severity order
export const POLICIES: HealthPolicyListResponse = {
  items: [
    policy("p1", "failed drive", "CRITICAL", { vendor: "dell" }, FAILED_DRIVE),
    policy("p2", "general warning", "WARNING", {}, FAILED_DRIVE),
    policy("p3", "Power supply failed", "CRITICAL", {}, node({
      any_of: [leaf("power.failed_psu_count", "GTE", 2), node({ all_of: [leaf("power.failed_psu_count", "EQ", 1), leaf("power.psu_count", "LTE", 1)] })],
    })),
    policy("p4", "general major", "MAJOR", {}, node({ not: leaf("raid.state", "EQ", "ABSENT") })),
    policy("p5", "cisco vnic down", "MAJOR", { vendor: "cisco", manager_types: ["UCS_CENTRAL", "INTERSIGHT"] }, leaf("connectivity.fabric_paths_down", "GTE", 1)),
    policy("p6", "lab memory", "WARNING", { site_id: "tlv" }, leaf("memory.degraded_dimm_count", "GTE", 1)),
  ],
};

type Handler = (route: Route) => Promise<void> | void;
type Answer = ClassificationRuleListResponse | HealthPolicyListResponse | Handler;

/**
 * An admin, the Sites read the top bar makes, and day1's two routes. Returns
 * how many times each was read. Register a test's own routes after this:
 * mocks match LIFO.
 */
export async function setUpRules(
  page: Page,
  { rules = RULES, policies = POLICIES, viewer = false, sites }: { rules?: Answer; policies?: Answer; viewer?: boolean; sites?: Handler } = {}
): Promise<{ reads: () => number }> {
  let reads = 0;
  await setUpServerScan(page, { viewer, ...(sites ? { sites } : {}) });
  const serve = (answer: Answer) => (route: Route) => {
    reads += 1;
    return typeof answer === "function" ? answer(route) : json(route, answer);
  };
  await page.route("**/api/day1/server-scan/classification-rules", serve(rules));
  await page.route("**/api/day1/server-scan/health-policies", serve(policies));
  return { reads: () => reads };
}
