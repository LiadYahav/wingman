/**
 * The tuning profiles a nodepool can name (`GET /api/day1/tuning-profiles`,
 * ADR-0061, docs/notes/2026-11-15-tuning-profiles-api.md): `Tuned` and
 * `PerformanceProfile` manifests in `tuning/` of the day1 repo, which the
 * day1 CI injects into the cluster file. A nodepool's input is a list of
 * names (`tuning_config`); a flavor can lock them on every nodepool as one
 * rule, compared as a set. Day1 is the authority: these checks only answer
 * sooner, and every problem day1 returns is still shown.
 */

import { useQuery } from "@tanstack/react-query";
import { day1Api, day1Keys } from "@/lib/api/day1";
import type { ComboboxOption } from "@/components/ui/combobox";
import type { TuningProfiles } from "@/types";

/** The nodepool input that names tuning profiles. */
export const TUNING = "tuning_config";
/** The rule: every nodepool has exactly these tuning profiles, in any order. */
export const TUNING_RULE = "nodepools[*].tuning_config";
/** Day1's limit per nodepool. */
const MAX_TUNING_PROFILES = 16;

/** What a person reads before choosing: where the profiles come from and what changing them costs. */
export const TUNING_HINT =
  "Tuned and PerformanceProfile manifests from tuning/ in the day1 repo. The nodepool names them; the day1 CI injects the manifests into the cluster file. Changing a nodepool's tuning can reboot its nodes (a PerformanceProfile, kernel arguments).";

/** The catalogue; cached a minute, like day1's own read. */
export function useTuningProfiles(enabled = true) {
  return useQuery<TuningProfiles>({
    queryKey: day1Keys.fleet.tuningProfiles,
    queryFn: day1Api.fleet.tuningProfiles,
    staleTime: 60_000,
    enabled,
  });
}

export const tuningPath = (index: number) => `nodepools[${index}].${TUNING}`;

/** `nodepools[<i>].tuning_config`: a field drawn with the tuning-profile picker. */
export function isTuningPath(path: string): boolean {
  return /^nodepools\[\d+\]\.tuning_config$/.test(path);
}

/** A `tuning_config` value as names: one name as a string (an older flavor) is a list of one. */
export function tuningNames(value: unknown): string[] {
  if (typeof value === "string") return value ? [value] : [];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item !== "");
}

/** Two lists name the same profiles, in any order, repeats aside (the rule's comparison). */
export function sameTuning(a: string[], b: string[]): boolean {
  const left = new Set(a);
  const right = new Set(b);
  return left.size === right.size && [...left].every((name) => right.has(name));
}

/**
 * The rule's names from a flavor's values: what every nodepool sets, which
 * must agree as a set and not be empty; `null` when they don't (day1 then
 * reports the rule in `warnings` and does not enforce it).
 */
export function tuningRuleNames(values: Record<string, unknown>): string[] | null {
  const pools = values.nodepools;
  if (!Array.isArray(pools) || pools.length === 0) return null;
  const lists = pools.map((pool) =>
    pool && typeof pool === "object" && !Array.isArray(pool) ? tuningNames((pool as Record<string, unknown>)[TUNING]) : []
  );
  const first = lists[0];
  if (first.length === 0 || lists.some((list) => !sameTuning(list, first))) return null;
  return first;
}

const PERFORMANCE = "PerformanceProfile";

/** The PerformanceProfiles among `names`, by the catalogue (a name it does not have is none). */
function performanceProfiles(names: string[], catalog: TuningProfiles | undefined): string[] {
  const kinds = new Map((catalog?.profiles ?? []).map((p) => [p.name, p.kind]));
  return names.filter((name) => kinds.get(name) === PERFORMANCE);
}

/** The picker's choices: every shared profile, grouped by kind, its summary (or path) below it. */
export function tuningOptions(catalog: TuningProfiles | undefined, chosen: string[]): ComboboxOption[] {
  const used = new Set(chosen);
  const held = performanceProfiles(chosen, catalog)[0];
  return (catalog?.profiles ?? []).map((p) => {
    const about = p.summary ? `${p.kind} · ${p.summary}` : `${p.kind} · ${p.path}`;
    const replaces = p.kind === PERFORMANCE && held && held !== p.name;
    return {
      value: p.name,
      label: p.name,
      description: replaces ? `${about} · A nodepool takes one PerformanceProfile; picking this replaces ${held}` : about,
      group: p.kind,
      disabled: used.has(p.name),
    };
  });
}

/**
 * `names` with `name` added at the end; a PerformanceProfile takes the place
 * of the one the nodepool has, since a NodePool references at most one
 * (HyperShift). Any number of Tuned profiles may be listed.
 */
export function addTuning(names: string[], name: string, catalog: TuningProfiles | undefined): string[] {
  if (names.includes(name)) return names;
  const kind = catalog?.profiles.find((p) => p.name === name)?.kind;
  const held = kind === PERFORMANCE ? performanceProfiles(names, catalog)[0] : undefined;
  return held ? names.map((n) => (n === held ? name : n)) : [...names, name];
}

/** Each Tuned in `names` that builds on a PerformanceProfile the list does not have: a warning, never a refusal. */
export function missingPerformanceProfiles(names: string[], catalog: TuningProfiles | undefined): { tuned: string; requires: string }[] {
  const byName = new Map((catalog?.profiles ?? []).map((p) => [p.name, p]));
  return names.flatMap((name) => {
    const requires = byName.get(name)?.requires_performance_profile;
    return requires && !names.includes(requires) ? [{ tuned: name, requires }] : [];
  });
}

/**
 * The problems day1 would report for a list at save or create (§3): a name
 * that is not a shared profile, a name listed twice, two PerformanceProfiles
 * (a NodePool references at most one), too many. With no
 * catalogue yet, names are not judged.
 */
export function tuningProblems(names: string[], catalog: TuningProfiles | undefined): string[] {
  const problems: string[] = [];
  const shared = new Set(catalog?.profiles.map((p) => p.name) ?? []);
  const seen = new Set<string>();
  for (const name of names) {
    if (seen.has(name)) problems.push(`${name} is listed twice`);
    else if (catalog && !shared.has(name)) problems.push(`${name} is not a tuning profile in ${catalog.folder}/`);
    seen.add(name);
  }
  const performance = performanceProfiles(names, catalog);
  if (performance.length > 1) {
    problems.push(`At most one PerformanceProfile per nodepool (HyperShift); it names ${performance.join(", ")}`);
  }
  if (names.length > MAX_TUNING_PROFILES) problems.push(`${names.length} profiles; the limit is ${MAX_TUNING_PROFILES}`);
  return problems;
}

/** Names for a summary line: `a, b`, or `none`. */
export function showTuning(names: string[]): string {
  return names.length > 0 ? names.join(", ") : "none";
}
