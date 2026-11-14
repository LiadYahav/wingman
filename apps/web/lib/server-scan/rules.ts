/**
 * The Rules & Policies page's words and order, as server-scan's page shows
 * them (docs/notes/2026-11-13-server-scan-area-api.md §13.1): a rule's scope
 * as one string, never a blank; the health policies grouped by scope, the
 * groups from general to site, the rows by severity then name; a policy's
 * condition as one line of text.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/features/rules/RulesPage.tsx`
 * (`scopeSummary`, `policyScopeLabel`, `policyScopeRank`, `policySections`,
 * `severityRank`, `conditionSummary`) and `MANAGER_TYPE_LABELS` of
 * `frontend/src/types/classification.ts`.
 */

import type { HealthSeverity } from "@/types/server-scan";
import type { ClassificationRuleResponse, Condition, HealthPolicyResponse, PolicyScope, RuleScope } from "@/types/server-scan-rules";
import { isAllOf, isAnyOf, isLeaf, isNot } from "@/types/server-scan-rules";
import { SEVERITY_ORDER, vendorLabel } from "./vocabulary";

/** Every collector (server-scan's `ManagerType`) as a person names it; vendor-free, so it can sit beside its vendor. */
const MANAGER_TYPE_LABELS: Record<string, string> = {
  UCS_CENTRAL: "UCS Central",
  UCS_MANAGER: "UCS Manager",
  INTERSIGHT: "Intersight",
  OPENMANAGE: "OpenManage",
  ONEVIEW: "OneView",
  REDFISH_STANDALONE: "Redfish standalone",
  KUBEVIRT: "KubeVirt",
};

/** A rule's scope as one string; `(unscoped)` rather than a blank that reads as missing data. */
export function scopeSummary(scope: RuleScope): string {
  const parts: string[] = [];
  if (scope.vendor) parts.push(`vendor=${scope.vendor}`);
  if (scope.manager_type) parts.push(`manager=${scope.manager_type}`);
  if (scope.site_id) parts.push(`site=${scope.site_id}`);
  return parts.length > 0 ? parts.join(", ") : "(unscoped)";
}

/** A rule's `field ~ pattern`. */
export const rulePattern = (rule: ClassificationRuleResponse): string => `${rule.field} ~ ${rule.pattern}`;

/** A policy scope as a section heading. */
export function policyScopeLabel(scope: PolicyScope): string {
  const parts: string[] = [];
  if (scope.vendor) parts.push(vendorLabel(scope.vendor));
  if (scope.manager_types.length > 0) parts.push(scope.manager_types.map((m) => MANAGER_TYPE_LABELS[m] ?? m).join(", "));
  if (scope.site_id) parts.push(`Site ${scope.site_id}`);
  return parts.length > 0 ? parts.join(" — ") : "General";
}

/** Sections come in specificity order: general, vendor, collector, site. */
export function policyScopeRank(scope: PolicyScope): number {
  if (scope.site_id) return 3;
  if (scope.manager_types.length > 0) return 2;
  if (scope.vendor) return 1;
  return 0;
}

export function severityRank(severity: HealthSeverity): number {
  const index = SEVERITY_ORDER.indexOf(severity);
  return index === -1 ? SEVERITY_ORDER.length : index;
}

export interface PolicySection {
  label: string;
  rank: number;
  policies: HealthPolicyResponse[];
}

/** Policies grouped by scope, sections by specificity then label, rows by severity then name. */
export function policySections(policies: HealthPolicyResponse[]): PolicySection[] {
  const byLabel = new Map<string, PolicySection>();
  for (const policy of policies) {
    const label = policyScopeLabel(policy.scope);
    const section = byLabel.get(label) ?? { label, rank: policyScopeRank(policy.scope), policies: [] };
    section.policies.push(policy);
    byLabel.set(label, section);
  }
  const sections = [...byLabel.values()];
  sections.sort((a, b) => a.rank - b.rank || a.label.localeCompare(b.label));
  for (const section of sections) {
    section.policies.sort((a, b) => severityRank(a.severity) - severityRank(b.severity) || a.name.localeCompare(b.name));
  }
  return sections;
}

/** A health policy's condition as one line of readable text. */
export function conditionSummary(condition: Condition): string {
  if (isAllOf(condition)) return condition.all_of.map(conditionSummary).join(" AND ");
  if (isAnyOf(condition)) return `(${condition.any_of.map(conditionSummary).join(" OR ")})`;
  if (isNot(condition)) return `NOT ${conditionSummary(condition.not)}`;
  if (isLeaf(condition)) {
    const parts = [condition.metric ?? "", condition.operator ?? ""];
    if (condition.value != null) parts.push(JSON.stringify(condition.value));
    // COUNT_* without `equals` counts the list's own length.
    if (condition.equals != null) parts.push(`of ${JSON.stringify(condition.equals)}`);
    return parts.join(" ");
  }
  return "—";
}

/** A policy's tooltip: what it is for, and what it says when it fires. */
export function policyHint(policy: HealthPolicyResponse): string {
  return [policy.description, `Says: ${policy.message_template}`].filter(Boolean).join("\n");
}
