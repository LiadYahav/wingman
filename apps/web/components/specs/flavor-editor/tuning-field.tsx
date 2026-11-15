"use client";

import { TuningProfilesPicker } from "@/components/tuning/tuning-profiles-picker";
import { TUNING, TUNING_RULE } from "@/lib/tuning-profiles";
import { ValueField } from "./controls";
import { nodepoolPath, type FlavorDraft } from "./model";
import { isTuningRule, poolTuning, setPoolTuning, setTuningRule } from "./tuning-model";

type Update = (change: (draft: FlavorDraft) => FlavorDraft) => void;

/**
 * A nodepool's tuning profiles (ADR-0061): a preset, or locked, which locks
 * them on every nodepool as one rule (`nodepools[*].tuning_config`). Under
 * the rule each nodepool's picker edits the one list every nodepool holds.
 */
export function TuningField({
  index,
  draft,
  update,
  problems,
  notEnforced,
}: {
  index: number;
  draft: FlavorDraft;
  update: Update;
  problems: (path: string, options?: { deeper?: boolean }) => string[];
  notEnforced: (path: string) => string | undefined;
}) {
  const path = nodepoolPath(index, TUNING);
  const rule = isTuningRule(draft);
  const names = poolTuning(draft, index);
  const shown = [...problems(path, { deeper: true }), ...(rule ? problems(TUNING_RULE, { deeper: true }) : [])];
  return (
    <ValueField
      path={path}
      label="Tuning profiles"
      locked={rule}
      onLockedChange={(locked) => update((d) => setTuningRule(d, locked, index))}
      notEnforced={rule ? notEnforced(TUNING_RULE) : undefined}
      empty={names.length === 0}
      problems={[...new Set(shown)]}
      labelsInput={false}
      hint={
        rule
          ? "Locked on every nodepool: each nodepool of every cluster has exactly these, in any order."
          : names.length === 0
            ? "Not set: each cluster may choose some. Lock to fix them on every nodepool."
            : "Prefilled: a cluster may change them. Lock to fix them on every nodepool."
      }
    >
      {() => (
        <TuningProfilesPicker
          names={names}
          onChange={(next) => update((d) => setPoolTuning(d, index, next))}
          localChecks={false}
          label={`Nodepool ${index + 1} tuning profiles`}
          testId={`nodepool-${index}-tuning`}
        />
      )}
    </ValueField>
  );
}
