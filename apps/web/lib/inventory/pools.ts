/**
 * Grouping and labels for each MCE's pools (ADR-0057). The numbers are
 * day1's (server-scan's counts); nothing is recounted here.
 */

import type { HardwareCount, MceInventory } from "@/types/inventory";

export interface SiteGroup {
  site: string;
  /** MCEs with something to show: servers in server-scan, or InfraEnvs to fill. */
  mces: MceInventory[];
  /** MCEs server-scan names nothing on and whose InfraEnvs are unknown: a name each. */
  quiet: MceInventory[];
}

/** Whether an MCE gets a card: server-scan knows it, or its hub lists pools to fill. */
const hasCard = (mce: MceInventory): boolean => mce.known || mce.pools.length > 0;

/** The MCEs by site, in day1's order. */
export function bySite(mces: MceInventory[]): SiteGroup[] {
  const groups = new Map<string, SiteGroup>();
  for (const mce of mces) {
    const group = groups.get(mce.site) ?? { site: mce.site, mces: [], quiet: [] };
    (hasCard(mce) ? group.mces : group.quiet).push(mce);
    groups.set(mce.site, group);
  }
  return [...groups.values()];
}

/** `dell PowerEdge R650`, or what server-scan gives. */
export function hardwareLabel(hardware: Pick<HardwareCount, "vendor" | "model">): string {
  return [hardware.vendor, hardware.model].filter(Boolean).join(" ") || "Unknown hardware";
}

/** Every MCE's available Agents, summed: the page's one headline number. */
export const totalAvailable = (mces: MceInventory[]): number =>
  mces.reduce((total, mce) => total + mce.available, 0);
