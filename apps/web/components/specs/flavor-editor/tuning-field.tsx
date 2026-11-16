"use client";

import { TuningProfilesPicker } from "@/components/tuning/tuning-profiles-picker";
import { TUNING, TUNING_RULE, showTuning } from "@/lib/tuning-profiles";
import { ValueField } from "./controls";
import { configsMode, nodepoolPath, type FlavorDraft } from "./model";
import { isTuningRule, poolTuning, setPoolTuning, setTuningRule } from "./tuning-model";

type Update = (change: (draft: FlavorDraft) => FlavorDraft) => void;

/** Where a preset's lock is, in one line: the card's own control, or the every-nodepool panel's switch. */
function presetHint(empty: boolean, panel: boolean): string {
  const start = empty ? "Not set: each cluster may choose some." : "Prefilled: a cluster may change them.";
  return `${start} ${panel ? "To lock them on every nodepool, use the switch under On every nodepool." : "Lock to fix them on every nodepool."}`;
}

/**
 * A nodepool's tuning profiles (ADR-0061): a preset, or locked, which locks
 * them on every nodepool as one rule (`nodepools[*].tuning_config`). With
 * configs the same on every nodepool, the rule is the panel's switch: on, the
 * card only names the rule's profiles; off, its picker is a preset. With
 * configs per nodepool, under the rule each picker edits the one list every
 * nodepool holds.
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
  const panel = configsMode(draft) === "rule";
  const names = poolTuning(draft, index);

  if (panel && rule) {
    return (
      <ValueField
        path={path}
        label="Tuning profiles"
        empty={names.length === 0}
        problems={problems(path, { deeper: true })}
        labelsInput={false}
        hint="Set under On every nodepool, above."
      >
        {() => (
          <p className="text-xs text-muted-foreground" data-testid={`nodepool-${index}-tuning-rule`}>
            Gets the rule&apos;s tuning profiles: <span className="font-mono text-foreground/80">{showTuning(names)}</span>
          </p>
        )}
      </ValueField>
    );
  }

  const shown = [...problems(path, { deeper: true }), ...(rule ? problems(TUNING_RULE, { deeper: true }) : [])];
  return (
    <ValueField
      path={path}
      label="Tuning profiles"
      locked={panel ? undefined : rule}
      onLockedChange={panel ? undefined : (locked) => update((d) => setTuningRule(d, locked, index))}
      notEnforced={rule ? notEnforced(TUNING_RULE) : undefined}
      empty={names.length === 0}
      problems={[...new Set(shown)]}
      labelsInput={false}
      hint={
        rule
          ? "Locked on every nodepool: each nodepool of every cluster has exactly these, in any order."
          : presetHint(names.length === 0, panel)
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
