import type { ReactNode } from "react";
import { conditionSummary, policyHint, policySections, rulePattern, scopeSummary } from "@/lib/server-scan/rules";
import { cn } from "@/lib/utils";
import type { ClassificationRuleResponse, HealthPolicyResponse } from "@/types/server-scan-rules";
import { SeverityPill, pill } from "./server-badges";

/**
 * The Rules & Policies page's tables, as server-scan's `RulesPage.tsx`
 * (team-redbull/server-scan at 92146d3, decision 18;
 * docs/notes/2026-11-13-server-scan-area-api.md §13.1): the classification
 * rules in the order server-scan tries them, and the health policies in a
 * table per scope. Read only: no control at all. A rule's or policy's
 * description is its name's tooltip.
 */

const RULE_COLUMNS = ["Name", "Type", "Matches", "Priority", "Scope"] as const;
const POLICY_COLUMNS = ["Name", "Category", "Severity", "Condition", "policy_key"] as const;

function Table({ label, columns, children }: { label: string; columns: readonly string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-xl border bg-card">
      <table aria-label={label} className="w-full border-collapse text-left text-sm">
        <thead className="bg-muted/60 text-xs text-muted-foreground">
          <tr className="border-b">
            {columns.map((column) => (
              <th key={column} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">{children}</tbody>
      </table>
    </div>
  );
}

/** A row in place of the rows when there are none, in server-scan's words. */
function NoRows({ columns, children }: { columns: number; children: ReactNode }) {
  return (
    <tr>
      <td colSpan={columns} className="px-3 py-6 text-center text-muted-foreground">
        {children}
      </td>
    </tr>
  );
}

function RuleRow({ rule }: { rule: ClassificationRuleResponse }) {
  return (
    <tr data-testid="ss-rule" data-rule={rule.id}>
      <td className="px-3 py-2 font-medium" title={rule.description || undefined}>
        {rule.name}
      </td>
      <td className="px-3 py-2">
        <span className={cn(pill, "bg-muted font-mono text-foreground/80")}>{rule.installation_type}</span>
      </td>
      <td className="px-3 py-2">
        <code className="font-mono text-xs">{rulePattern(rule)}</code>
        {rule.flags.ignore_case && <span className="ml-2 text-xs text-muted-foreground">(case-insensitive)</span>}
      </td>
      <td className="px-3 py-2 tabular-nums">{rule.priority}</td>
      <td className="px-3 py-2 text-muted-foreground">{scopeSummary(rule.scope)}</td>
    </tr>
  );
}

/** The classification rules, in server-scan's order (highest priority first; the first match wins). */
export function RulesTable({ rules }: { rules: ClassificationRuleResponse[] }) {
  return (
    <Table label="Classification rules" columns={RULE_COLUMNS}>
      {rules.map((rule) => (
        <RuleRow key={rule.id} rule={rule} />
      ))}
      {rules.length === 0 && <NoRows columns={RULE_COLUMNS.length}>No classification rules are configured.</NoRows>}
    </Table>
  );
}

function PolicyRow({ policy }: { policy: HealthPolicyResponse }) {
  return (
    <tr data-testid="ss-policy" data-policy={policy.id}>
      <td className="px-3 py-2 font-medium" title={policyHint(policy)}>
        {policy.name}
      </td>
      <td className="px-3 py-2">{policy.category}</td>
      <td className="px-3 py-2">
        <SeverityPill severity={policy.severity} />
      </td>
      <td className="px-3 py-2">
        <code className="font-mono text-xs">{conditionSummary(policy.condition)}</code>
      </td>
      <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{policy.policy_key}</td>
    </tr>
  );
}

/** The health policies, a table per scope: General first, then vendor, collector and site; rows by severity, then name. */
export function PolicySections({ policies }: { policies: HealthPolicyResponse[] }) {
  if (policies.length === 0) {
    return (
      <p className="rounded-xl border bg-card px-3 py-6 text-center text-sm text-muted-foreground" data-testid="ss-policies-none">
        No health policies are configured.
      </p>
    );
  }
  return (
    <div className="space-y-6">
      {policySections(policies).map((section) => (
        <section key={section.label} aria-label={section.label} data-testid="ss-policy-section" className="space-y-2">
          <h3 className="text-base font-semibold">{section.label}</h3>
          {section.rank === 0 && <p className="text-sm text-muted-foreground">Applies to every server, whatever collected it.</p>}
          <Table label={`Health policies: ${section.label}`} columns={POLICY_COLUMNS}>
            {section.policies.map((policy) => (
              <PolicyRow key={policy.id} policy={policy} />
            ))}
          </Table>
        </section>
      ))}
    </div>
  );
}
