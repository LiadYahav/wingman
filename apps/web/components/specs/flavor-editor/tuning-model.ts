/**
 * The flavor editor's tuning profiles (ADR-0061,
 * docs/notes/2026-11-15-tuning-profiles-api.md §2-§4): each nodepool's
 * `tuning_config` is a list of names, a preset; or the rule
 * `nodepools[*].tuning_config` locks the same names on every nodepool,
 * compared as a set. Under the rule every nodepool holds the rule's names,
 * so the flavor's values always agree, as day1's save requires. With the
 * configs "the same on every nodepool" (ADR-0029), the tuning rule is part
 * of that one panel, on by default (ADR-0061's 2026-11-16 amendment).
 */

import { TUNING, TUNING_RULE, sameTuning, tuningNames, tuningProblems } from "@/lib/tuning-profiles";
import type { ConfigEntry, TuningProfiles } from "@/types";
import {
  configsMode,
  nodepoolCount,
  nodepoolPath,
  nodepoolValues,
  setConfigsMode,
  setNodepoolValue,
  type ConfigsMode,
  type FlavorDraft,
  type Issue,
} from "./model";

export const isTuningRule = (draft: FlavorDraft) => draft.locked.includes(TUNING_RULE);

export function poolTuning(draft: FlavorDraft, index: number): string[] {
  return tuningNames(nodepoolValues(draft, index)[TUNING]);
}

/** Every nodepool names the same profiles as the first, as a set (none count as the same). */
export function tuningAgrees(draft: FlavorDraft): boolean {
  const first = nodepoolCount(draft) > 0 ? poolTuning(draft, 0) : [];
  return Array.from({ length: nodepoolCount(draft) }, (_, i) => poolTuning(draft, i)).every((names) => sameTuning(names, first));
}

/** Every nodepool's tuning at `names`; none is no key. */
function withEveryPool(draft: FlavorDraft, names: string[]): FlavorDraft {
  let next = draft;
  for (let i = 0; i < nodepoolCount(draft); i++) next = setNodepoolValue(next, i, TUNING, names.length > 0 ? [...names] : undefined);
  return next;
}

/** One nodepool's profiles; under the rule, every nodepool's. */
export function setPoolTuning(draft: FlavorDraft, index: number, names: string[]): FlavorDraft {
  if (isTuningRule(draft)) return withEveryPool(draft, names);
  return setNodepoolValue(draft, index, TUNING, names.length > 0 ? names : undefined);
}

/**
 * Lock the profiles on every nodepool (the rule), starting from `index`'s, or
 * unlock them: each nodepool then keeps the names as its own preset.
 */
export function setTuningRule(draft: FlavorDraft, on: boolean, index: number): FlavorDraft {
  if (on === isTuningRule(draft)) return draft;
  if (!on) return { ...draft, locked: draft.locked.filter((p) => p !== TUNING_RULE) };
  const names = poolTuning(draft, index);
  return withEveryPool({ ...draft, locked: [...draft.locked, TUNING_RULE] }, names);
}

/**
 * Switch the configs between each nodepool's own and the same on every
 * nodepool, tuning included. Entering the rule turns the tuning rule on from
 * Nodepool 1's names, unless the nodepools name different profiles (nothing
 * is overwritten) or `offered` is false (the catalogue lists none). Leaving
 * it drops both rules: each nodepool keeps its configs and names as presets.
 */
export function chooseConfigsMode(
  draft: FlavorDraft,
  mode: ConfigsMode,
  defaults: ConfigEntry[],
  hardware: string | null,
  offered: boolean
): FlavorDraft {
  if (configsMode(draft) === mode) return draft;
  const next = setConfigsMode(draft, mode, defaults, hardware);
  if (mode === "each") return setTuningRule(next, false, 0);
  if (isTuningRule(next) || !offered || !tuningAgrees(next)) return next;
  return setTuningRule(next, true, 0);
}

/** After a nodepool is added: under the rule it gets the rule's names (the first nodepool's). */
export function keepTuningRule(draft: FlavorDraft): FlavorDraft {
  return isTuningRule(draft) && nodepoolCount(draft) > 0 ? withEveryPool(draft, poolTuning(draft, 0)) : draft;
}

/** The fields day1's tuning problems are shown at. */
export function tuningFields(draft: FlavorDraft): string[] {
  const fields = Array.from({ length: nodepoolCount(draft) }, (_, i) => nodepoolPath(i, TUNING));
  return isTuningRule(draft) ? [TUNING_RULE, ...fields] : fields;
}

/**
 * What day1 would refuse at save (§3, §4), at the fields it belongs to. In
 * the every-nodepool panel the rule's names are checked once, at the panel;
 * otherwise each nodepool's at its own field.
 */
export function tuningIssues(draft: FlavorDraft, catalog: TuningProfiles | undefined): Issue[] {
  const issues: Issue[] = [];
  const rule = isTuningRule(draft);
  const panel = rule && configsMode(draft) === "rule";
  const first = nodepoolCount(draft) > 0 ? poolTuning(draft, 0) : [];
  if (panel) {
    for (const message of tuningProblems(first, catalog)) issues.push({ path: TUNING_RULE, message });
  } else {
    for (let i = 0; i < nodepoolCount(draft); i++) {
      for (const message of tuningProblems(poolTuning(draft, i), catalog)) issues.push({ path: nodepoolPath(i, TUNING), message });
    }
  }
  if (rule && first.length === 0) {
    issues.push({
      path: TUNING_RULE,
      message: panel
        ? "Choose the profiles every nodepool gets, or turn off the same tuning profiles"
        : "Choose at least one profile to lock, or make the tuning profiles a preset",
    });
  }
  return issues;
}
