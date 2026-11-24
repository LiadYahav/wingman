/**
 * The Create Customer MCE preview's arithmetic (ADR-0018's 2026-11-24
 * amendment): the platform's design for a new Customer MCE, worked out from
 * the MCE list the page already holds. Pure: nothing is read or written here,
 * and nothing creates an MCE (a person installs one by hand today).
 */

import { isSeed } from "@/lib/workspaces";
import type { Mce } from "@/types";

/** The naming convention's lifecycles (`ocp4-<lifecycle>-mce-<site>-<id>`). */
export const LIFECYCLES = ["prod", "prep", "test"] as const;
export type Lifecycle = (typeof LIFECYCLES)[number];

/** Every MCE VM's size: `kv32`, 32 vCPU and 128 GiB (the platform's MCE VM). */
export const MCE_VM = { size: "kv32", vcpu: 32, memoryGiB: 128 } as const;

/** Workers per zone the preview offers: P11's three worker VMs are one per zone. */
export const WORKERS_PER_ZONE = { min: 1, max: 5 } as const;

const LETTERS = "abcdefghijklmnopqrstuvwxyz";

const byName = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true });

/** The sites the day1 repo has MCE-level folders at (Customer MCEs and seeds), by name. */
export function previewSites(mces: readonly Mce[]): string[] {
  return [...new Set(mces.map((mce) => mce.site))].sort(byName);
}

/** A site's zones: one per seed that names its zone, by name. */
export function siteZones(mces: readonly Mce[], site: string): string[] {
  const zones = mces.filter((mce) => isSeed(mce) && mce.site === site && mce.zone).map((mce) => mce.zone as string);
  return [...new Set(zones)].sort(byName);
}

/** The site to start on: the first with a seed, so the preview has zones to show; else the first. */
export function firstSite(mces: readonly Mce[]): string | null {
  const sites = previewSites(mces);
  return sites.find((site) => siteZones(mces, site).length > 0) ?? sites[0] ?? null;
}

/** The `<id>` letters the site's Customer MCEs hold: day1's `letter`, or the name's last segment. */
function lettersInUse(mces: readonly Mce[], site: string): Set<string> {
  const used = new Set<string>();
  for (const mce of mces) {
    if (isSeed(mce) || mce.site !== site) continue;
    const letter = mce.letter ?? /-([a-z])$/.exec(mce.name)?.[1];
    if (letter) used.add(letter);
  }
  return used;
}

/** The next free `<id>`, `a` to `z`, among the site's Customer MCEs; `null` once all 26 are taken. */
export function nextMceLetter(mces: readonly Mce[], site: string): string | null {
  const used = lettersInUse(mces, site);
  return [...LETTERS].find((letter) => !used.has(letter)) ?? null;
}

/** The new MCE's name, `ocp4-<lifecycle>-mce-<site>-<id>`; `null` when the site has no letter left. */
export function previewMceName(mces: readonly Mce[], site: string, lifecycle: Lifecycle): string | null {
  const letter = nextMceLetter(mces, site);
  return letter ? `ocp4-${lifecycle}-mce-${site}-${letter}` : null;
}

export interface VmPlan {
  masters: number;
  workers: number;
  vms: number;
  vcpu: number;
  memoryGiB: number;
}

/** One master VM per zone (AD19) and the workers spread over the zones (AD20), every VM a `kv32`. */
export function vmPlan(zones: number, workersPerZone: number): VmPlan {
  const workers = zones * workersPerZone;
  const vms = zones + workers;
  return { masters: zones, workers, vms, vcpu: vms * MCE_VM.vcpu, memoryGiB: vms * MCE_VM.memoryGiB };
}

/** Why the typed OpenShift version is not one yet (`4.20`, `4.20.44`); `null` when it is, or is empty. */
export function versionProblem(typed: string): string | null {
  const version = typed.trim();
  if (version === "" || /^4\.\d{1,2}(\.\d{1,3})?$/.test(version)) return null;
  return "An OpenShift version, such as 4.20 or 4.20.44.";
}

/** The workers per zone as a count the preview offers, from a step or a typed value. */
export function workersPerZone(value: number): number {
  if (!Number.isFinite(value)) return WORKERS_PER_ZONE.min;
  return Math.min(WORKERS_PER_ZONE.max, Math.max(WORKERS_PER_ZONE.min, Math.round(value)));
}
