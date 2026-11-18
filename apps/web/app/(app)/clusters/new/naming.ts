/**
 * The naming convention (ADR-0014), mirrored from day1's domain/names.py
 * for the create form. The server is authoritative; this only gives the
 * hint while typing.
 */

import { PLACEMENT_ENVS, type PlacementEnv } from "@/lib/placement";
import type { Mce } from "@/types";

const DNS_LABEL = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?$/;
const MAX_DNS_LABEL = 63;

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** `ocp4-<env>-<name>-<site>[-<seq>]` for one site; group 1 is the env. */
function clusterNamePattern(site: string) {
  return new RegExp(
    `^ocp4-(prod|prep|test)-([a-z0-9](?:[-a-z0-9]*[a-z0-9])?)-${escapeRegExp(site)}(?:-([a-z0-9]+))?$`
  );
}

/** Why the server would refuse `name` under `site` and `mce`; `siteMces` once they have loaded. */
export function nameProblems(name: string, site: string, mce: Mce | undefined, siteMces: Mce[] | undefined): string[] {
  const problems: string[] = [];
  if (name.length > MAX_DNS_LABEL) problems.push(`Longer than ${MAX_DNS_LABEL} characters`);
  if (!DNS_LABEL.test(name)) {
    problems.push("Use lowercase letters, digits and '-', starting and ending with a letter or digit");
  }
  if (!site) return problems;
  const match = clusterNamePattern(site).exec(name);
  if (match?.[3] !== undefined && !/^[a-z]$/.test(match[3])) {
    problems.push(`The sequence "${match[3]}" must be one letter, a to z (-a, -b, …): a number is not the convention`);
  }
  if (!match) {
    problems.push(`Does not follow ocp4-<env>-<name>-${site}[-<letter>]`);
  } else if (mce) {
    if (mce.follows_convention && mce.env && match[1] !== mce.env) {
      problems.push(`Env "${match[1]}" does not match ${mce.name} (env "${mce.env}")`);
    }
  } else if (siteMces && !siteMces.some((m) => m.follows_convention && m.env === match[1])) {
    problems.push(`No "${match[1]}" MCE on ${site} follows the convention, so this env cannot be created there`);
  }
  return problems;
}

/** The site whose convention the name follows; the longest wins (`site-a` over `site`). */
export function siteFromName(name: string, sites: string[]): string | null {
  const matches = sites.filter((s) => clusterNamePattern(s).test(name));
  return matches.sort((a, b) => b.length - a.length)[0] ?? null;
}

/** The env a name following the site's convention carries, when a cluster can be placed in it (prod or prep). */
export function envFromName(name: string, site: string): PlacementEnv | null {
  const env = clusterNamePattern(site).exec(name)?.[1];
  return PLACEMENT_ENVS.find((e) => e === env) ?? null;
}
