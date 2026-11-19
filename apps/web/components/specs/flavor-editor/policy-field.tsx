"use client";

import { PolicySelect } from "@/components/clusters/policy-select";
import { offersPolicy, policyOf, POLICY_INPUT } from "@/lib/nodepool-policy";
import type { TemplateField } from "@/types";
import { ValueField } from "./controls";
import { isLocked, nodepoolPath, nodepoolValues, setLocked, setNodepoolValue, type FlavorDraft } from "./model";

type Update = (change: (draft: FlavorDraft) => FlavorDraft) => void;

/**
 * A flavor nodepool's scale-down policy (ADR-0062): a preset a cluster may
 * change, or locked, so every cluster the flavor creates has it on that
 * nodepool and drift and a sync keep it. A lock fixes a policy, never the
 * platform default (day1 refuses that). Shown when day1's template schema
 * offers the input, or the flavor already sets it.
 */
export function PolicyField({
  index,
  draft,
  update,
  schema,
  problems,
  notEnforced,
}: {
  index: number;
  draft: FlavorDraft;
  update: Update;
  schema: TemplateField[];
  problems: (path: string, options?: { deeper?: boolean }) => string[];
  notEnforced: (path: string) => string | undefined;
}) {
  const path = nodepoolPath(index, POLICY_INPUT);
  const value = nodepoolValues(draft, index)[POLICY_INPUT];
  if (!offersPolicy(schema) && value === undefined) return null;
  const locked = isLocked(draft, path);
  const empty = policyOf(value) === null;
  return (
    <ValueField
      path={path}
      label="Scale-down policy"
      locked={locked}
      onLockedChange={(next) => update((d) => setLocked(d, path, next))}
      notEnforced={notEnforced(path)}
      empty={empty}
      problems={problems(path, { deeper: true })}
      labelsInput={false}
      hint={locked && empty ? "Choose a policy to lock: the platform default cannot be locked." : undefined}
    >
      {() => (
        <PolicySelect
          value={value}
          onChange={(policy) => update((d) => setNodepoolValue(d, index, POLICY_INPUT, policy ?? undefined))}
          label={`Nodepool ${index + 1} scale-down policy`}
          testId={`nodepool-${index}-scale-down-policy`}
        />
      )}
    </ValueField>
  );
}
