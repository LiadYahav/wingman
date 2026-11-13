/**
 * Where the Install servers dialog sends a start (ADR-0057's amendment): an
 * MCE of the day1 repo and an InfraEnv, picked from what the page already
 * knows or typed. As on the orchestrator's own form, the InfraEnv is only
 * checked to be a name (a DNS label): whether the MCE has it is the
 * workflow's first check (`validating-infraenv`), a failed run otherwise.
 */

import type { InventoryRun, MceInventory } from "@/types/inventory";

/** One choice of a picker (the shape the shared `Combobox` takes). */
export interface PickerOption {
  value: string;
  label: string;
  description?: string;
  group?: string;
}

/** The InfraEnv choice that reveals a text field for a name the lists lack. */
export const OTHER_INFRA_ENV = "\u0000other";

/** Kubernetes' limit for a DNS-1123 label. */
const MAX_LABEL = 63;
const DNS_LABEL = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/;

/** Where a start goes; either part may still be unchosen. */
export interface InstallTarget {
  mce: string | null;
  infraEnv: string | null;
}

/** Why `value` is not an InfraEnv name (a DNS label), or `null` when it is one. */
export function infraEnvProblem(value: string): string | null {
  if (!value) return "Give the InfraEnv's name.";
  if (value.length > MAX_LABEL) return `At most ${MAX_LABEL} characters.`;
  if (!DNS_LABEL.test(value)) return "Lowercase letters, digits and '-', starting and ending with a letter or digit.";
  return null;
}

/**
 * The InfraEnvs the page knows on `mce`: its pools (the MCE's own list, or
 * the ones its cluster files name), then those its pool-draw runs filled, in
 * name order.
 */
export function knownInfraEnvs(mce: MceInventory | undefined, runs: readonly InventoryRun[] = []): string[] {
  if (!mce) return [];
  const names = new Set<string>();
  for (const pool of mce.pools) if (pool.infra_env) names.add(pool.infra_env);
  for (const run of runs) if (run.mce === mce.mce && run.infra_env) names.add(run.infra_env);
  return [...names].sort();
}

/** The day1 MCEs, grouped by site, for the MCE picker. */
export function mceOptions(mces: readonly MceInventory[]): PickerOption[] {
  return mces.map((m) => ({
    value: m.mce,
    label: m.mce,
    group: m.site,
    description: m.known ? `${m.available} available` : "not in server-scan",
  }));
}

/** The InfraEnv picker's choices: the known ones, then "Another InfraEnv…". */
export function infraEnvOptions(known: readonly string[], mce: MceInventory | undefined): PickerOption[] {
  const pools = new Map((mce?.pools ?? []).map((p) => [p.infra_env, p]));
  return [
    ...known.map((name) => {
      const pool = pools.get(name);
      return { value: name, label: name, description: pool ? `${pool.available} available` : "seen in the runs" };
    }),
    { value: OTHER_INFRA_ENV, label: "Another InfraEnv…", description: "Type its name" },
  ];
}

/** What a pool draw could pick in this pool, as server-scan counts it; `null` when not known. */
export function drawableIn(mce: MceInventory | undefined, infraEnv: string | null): number | null {
  if (!mce || !infraEnv) return null;
  return mce.pools.find((p) => p.infra_env === infraEnv)?.drawable ?? null;
}

/** The InfraEnv the dialog would send: the picked one, or the typed one once it is a DNS label. */
export function chosenInfraEnv(picked: string | null, typed: string): string | null {
  if (picked === null) return null;
  if (picked !== OTHER_INFRA_ENV) return picked;
  const name = typed.trim();
  return infraEnvProblem(name) === null ? name : null;
}
