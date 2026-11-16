"use client";

import { useId, type ReactNode } from "react";
import { Info, Lock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { ConfigListEditor } from "@/components/machine-configs/config-list-editor";
import { TuningProfilesPicker } from "@/components/tuning/tuning-profiles-picker";
import { NETWORK_CONFIG } from "@/lib/machine-configs";
import { TUNING_RULE, showTuning, useTuningProfiles } from "@/lib/tuning-profiles";
import { cn } from "@/lib/utils";
import type { MachineConfigs } from "@/types";
import { fieldId, NotEnforced } from "./controls";
import { CONFIGS_RULE, ruleEntries, setRuleEntries, type FlavorDraft } from "./model";
import { isTuningRule, poolTuning, setPoolTuning, setTuningRule, tuningAgrees } from "./tuning-model";

type Update = (change: (draft: FlavorDraft) => FlavorDraft) => void;
type Problems = (path: string, options?: { deeper?: boolean }) => string[];

function RuleBadge({ notEnforced }: { notEnforced: string | undefined }) {
  return (
    <Badge className={cn("gap-1", notEnforced && "bg-status-warning/15 text-status-warning-fg ring-status-warning/30")}>
      <Lock aria-hidden /> Locked as a rule{notEnforced ? ", not enforced" : ""}
    </Badge>
  );
}

function PartHeading({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
      <h4 className="text-[13px] font-medium text-foreground/90">
        {title}
      </h4>
      {children}
    </div>
  );
}

/**
 * The configs and, when its switch is on, the tuning profiles every nodepool
 * of every cluster has (ADR-0029, ADR-0061 and its 2026-11-16 amendment):
 * each locked as a rule, compared as a set. Each nodepool picks only its
 * network hardware.
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
  problems: Problems;
  notEnforced: (path: string) => string | undefined;
}) {
  const headingId = useId();
  const configsLock = notEnforced(CONFIGS_RULE);
  return (
    <div
      role="group"
      aria-labelledby={headingId}
      className="space-y-4 rounded-xl border border-primary/25 bg-primary/[0.04] p-4"
      data-testid="configs-rule"
    >
      <div className="min-w-0">
        <h3 id={headingId} className="text-sm font-semibold">
          On every nodepool
        </h3>
        <p className="text-xs text-muted-foreground">
          Every nodepool of every cluster gets these, in any order. Each nodepool below picks its own network hardware.
        </p>
      </div>

      <div id={fieldId(CONFIGS_RULE)} className="scroll-mt-28 space-y-2.5">
        <div className="space-y-0.5">
          <PartHeading title="Machine configs">
            <RuleBadge notEnforced={configsLock} />
          </PartHeading>
          <p className="text-xs text-muted-foreground">
            Exactly these on every nodepool. {NETWORK_CONFIG} is each nodepool&apos;s own network config.
          </p>
        </div>
        {configsLock && (
          <div className="text-xs">
            <NotEnforced reason={configsLock} />
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

      <RuleTuning draft={draft} update={update} problems={problems} notEnforced={notEnforced} />
    </div>
  );
}

/**
 * The panel's tuning profiles: a switch, on by default when the panel is
 * chosen. On, one picker edits every nodepool's names (the rule); off, each
 * nodepool card keeps its own picker, a preset.
 */
function RuleTuning({
  draft,
  update,
  problems,
  notEnforced,
}: {
  draft: FlavorDraft;
  update: Update;
  problems: Problems;
  notEnforced: (path: string) => string | undefined;
}) {
  const { data: tuning } = useTuningProfiles();
  const aboutId = useId();
  const on = isTuningRule(draft);
  const first = poolTuning(draft, 0);
  const lock = on ? notEnforced(TUNING_RULE) : undefined;
  // Nothing to choose: the switch stays off (a saved rule can still be turned off)
  const nothingOffered = tuning !== undefined && tuning.profiles.length === 0;
  return (
    <div className="space-y-2.5 border-t border-primary/15 pt-4" data-testid="rule-tuning-part">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-0.5">
          <PartHeading title="Tuning profiles">
            {on && <RuleBadge notEnforced={lock} />}
          </PartHeading>
          <p id={aboutId} className="text-xs text-muted-foreground">
            {on
              ? "On: exactly these on every nodepool, in any order."
              : "Off: each nodepool below sets its own, as a preset. Turn on to lock the same profiles on every nodepool."}
          </p>
        </div>
        <Switch
          aria-label="Same tuning profiles on every nodepool"
          aria-describedby={aboutId}
          checked={on}
          disabled={!on && nothingOffered}
          onCheckedChange={(checked) => update((d) => setTuningRule(d, checked, 0))}
          className="mt-0.5"
          data-testid="rule-tuning-switch"
        />
      </div>
      {on ? (
        <div id={fieldId(TUNING_RULE)} className="scroll-mt-28 space-y-2">
          {lock && (
            <div className="text-xs">
              <NotEnforced reason={lock} />
            </div>
          )}
          <TuningProfilesPicker
            names={first}
            onChange={(next) => update((d) => setPoolTuning(d, 0, next))}
            localChecks={false}
            problems={[...new Set(problems(TUNING_RULE, { deeper: true }))]}
            label="Tuning profiles on every nodepool"
            testId="rule-tuning"
          />
        </div>
      ) : nothingOffered ? (
        <p className="text-xs text-muted-foreground" data-testid="rule-tuning-none">
          {tuning.folder}/ in the day1 repo offers no tuning profile.
        </p>
      ) : (
        !tuningAgrees(draft) && (
          <p className="flex items-start gap-1.5 text-xs text-muted-foreground" data-testid="rule-tuning-differ">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            <span className="min-w-0 break-words">
              The nodepools name different tuning profiles, so each keeps its own. Turning this on gives every nodepool
              Nodepool 1&apos;s: <span className="font-mono text-foreground/80">{showTuning(first)}</span>.
            </span>
          </p>
        )
      )}
    </div>
  );
}
