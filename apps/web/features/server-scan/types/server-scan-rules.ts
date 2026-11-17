/**
 * The Server Scan area's Rules & Policies page: what server-scan runs, which
 * day1 passes through typed and in its own shapes
 * (docs/notes/2026-11-13-server-scan-area-api.md §13, ADR-0048's 3.30.0
 * amendment). Read only: both ship in server-scan's code.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/types/classification.ts` and
 * `frontend/src/types/health.ts`, their response types and guards. A word
 * server-scan adds later (a collector, an operator) still arrives as a string.
 */

import type { HealthSeverity, InstallationType } from "./server-scan";

// ── GET /api/day1/server-scan/classification-rules ────────────────────────────

/** The vendor, collector and site a rule is kept to; all `null`: every server. */
export interface RuleScope {
  vendor: string | null;
  manager_type: string | null;
  site_id: string | null;
}

export interface ClassificationRuleResponse {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  system: boolean;
  installation_type: InstallationType;
  scope: RuleScope;
  field: string;
  pattern: string;
  flags: { ignore_case: boolean; multiline: boolean; dotall: boolean };
  /** `SYSTEM_DEFAULT`, or a custom band: `SITE_CUSTOM`, `MANAGER_CUSTOM`, `VENDOR_CUSTOM`, `GLOBAL_CUSTOM`. */
  source: string;
  priority: number;
  order: number;
  stats: { last_matched_at: string | null; timeout_count: number; quarantined: boolean };
  revision: number;
  created_at: string;
  updated_at: string;
  created_by: string | null;
  updated_by: string | null;
}

export interface ClassificationRuleListResponse {
  /** The enabled rules, in the order server-scan tries them. */
  items: ClassificationRuleResponse[];
}

// ── GET /api/day1/server-scan/health-policies ─────────────────────────────────

/**
 * A condition tree node. One flat interface, not a discriminated union:
 * server-scan dumps every field on every node with the unused ones `null`,
 * so the guards below test nullness, not presence.
 */
export interface Condition {
  all_of?: Condition[] | null;
  any_of?: Condition[] | null;
  not?: Condition | null;
  metric?: string | null;
  operator?: string | null;
  value?: unknown;
  equals?: unknown;
}

export function isLeaf(c: Condition): boolean {
  return c.metric != null;
}
export function isAllOf(c: Condition): c is Condition & { all_of: Condition[] } {
  return c.all_of != null;
}
export function isAnyOf(c: Condition): c is Condition & { any_of: Condition[] } {
  return c.any_of != null;
}
export function isNot(c: Condition): c is Condition & { not: Condition } {
  return c.not != null;
}

/** The site, vendor and collectors a policy is kept to; none set: every server. */
export interface PolicyScope {
  site_id: string | null;
  vendor: string | null;
  manager_types: string[];
}

export interface HealthPolicyResponse {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  system: boolean;
  /** Policies sharing a key are one family: the highest-precedence one is evaluated. */
  policy_key: string;
  mode: string;
  category: string;
  severity: HealthSeverity;
  condition: Condition;
  evidence: { key: string; metric: string }[];
  message_template: string;
  scope: PolicyScope;
  source: string;
  priority: number;
  order: number;
  stats: { fire_count: number; last_fired_at: string | null; error_count: number; quarantined: boolean };
  revision: number;
  created_at: string;
  updated_at: string;
  created_by: string | null;
  updated_by: string | null;
}

export interface HealthPolicyListResponse {
  /** The enabled policies, in server-scan's database order (the page sorts them). */
  items: HealthPolicyResponse[];
}
