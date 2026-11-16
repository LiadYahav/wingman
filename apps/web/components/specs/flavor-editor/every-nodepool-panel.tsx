"use client";

import { Lock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ConfigListEditor } from "@/components/machine-configs/config-list-editor";
import { NETWORK_CONFIG } from "@/lib/machine-configs";
import { cn } from "@/lib/utils";
import type { MachineConfigs } from "@/types";
import { fieldId, NotEnforced } from "./controls";
import { CONFIGS_RULE, ruleEntries, setRuleEntries, type FlavorDraft } from "./model";

type Update = (change: (draft: FlavorDraft) => FlavorDraft) => void;

/**
 * The configs every nodepool of every cluster has, locked as one rule
 * (ADR-0029), compared as a set. Each nodepool picks only its network
 * hardware.
 */
export function EveryNodepoolPanel({
  draft,
  update,
  catalog,
  catalogLoading,
  problems,
  notEnforced,
}: {
  draft: FlavorDraft;
  update: Update;
  catalog: MachineConfigs | undefined;
  catalogLoading: boolean;
  problems: (path: string, options?: { deeper?: boolean }) => string[];
  notEnforced: (path: string) => string | undefined;
}) {
  return (
    <div id={fieldId(CONFIGS_RULE)} className="scroll-mt-28 space-y-3 rounded-xl border border-primary/25 bg-primary/[0.04] p-4" data-testid="configs-rule">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">Machine configs on every nodepool</h3>
          <p className="text-xs text-muted-foreground">
            Every nodepool of every cluster has exactly these, in any order. {NETWORK_CONFIG} is each nodepool&apos;s own
            network config.
          </p>
        </div>
        <Badge
          className={cn(
            "gap-1",
            notEnforced(CONFIGS_RULE) && "bg-status-warning/15 text-status-warning-fg ring-status-warning/30"
          )}
        >
          <Lock aria-hidden /> Locked as a rule{notEnforced(CONFIGS_RULE) ? ", not enforced" : ""}
        </Badge>
      </div>
      {notEnforced(CONFIGS_RULE) && (
        <div className="text-xs">
          <NotEnforced reason={notEnforced(CONFIGS_RULE)!} />
        </div>
      )}
      <ConfigListEditor
        entries={ruleEntries(draft)}
        onChange={(entries) => update((d) => setRuleEntries(d, entries))}
        catalog={catalog}
        loading={catalogLoading}
        networkHardware="per-nodepool"
        label="Machine configs on every nodepool"
        hideLabel
        testId="rule-configs"
      />
      {problems(CONFIGS_RULE).length > 0 && (
        <ul role="alert" className="space-y-0.5 text-xs text-destructive">
          {problems(CONFIGS_RULE).map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
