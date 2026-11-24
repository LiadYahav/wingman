/**
 * Labels for each MCE's pools, and the MCE the page opens on (ADR-0057). The
 * numbers are day1's (server-scan's counts); nothing is recounted here.
 */

import type { HardwareCount, MceInventory, PoolNames } from "@/types/inventory";

/** Whether an MCE has something to show: servers in server-scan, or InfraEnvs to fill. */
const hasPools = (mce: MceInventory): boolean => mce.known || mce.pools.length > 0;

/** The MCE the page shows when none is chosen: the first, in day1's order, with something to show. */
export const firstWithPools = (mces: readonly MceInventory[]): MceInventory | undefined =>
  mces.find(hasPools) ?? mces[0];

/** `dell PowerEdge R650`, or what server-scan gives. */
export function hardwareLabel(hardware: Pick<HardwareCount, "vendor" | "model">): string {
  return [hardware.vendor, hardware.model].filter(Boolean).join(" ") || "Unknown hardware";
}

/** Every MCE's available Agents, summed: the page's one headline number. */
export const totalAvailable = (mces: MceInventory[]): number =>
  mces.reduce((total, mce) => total + mce.available, 0);

/** How a pool draw names its servers: the InfraEnv's labels, never its name or its zone. */
export const POOL_NAMES_HINT =
  "A pool draw takes a free server named ocp-<flavor>-<size>-<site>-…, from the InfraEnv's agentLabels redbull.io/flavor, redbull.io/size and redbull.io/site. The zone is in no server's name, so the InfraEnvs of one flavor in several zones draw from the same servers.";

/**
 * Why a pool's servers are not known by name, or `null` when its InfraEnv's
 * agentLabels name them: its labels lack one (the workflow refuses a pool
 * draw into it), or they were not read (live status off, the MCE unreadable).
 */
export function unnamedReason(pool: PoolNames): string | null {
  if (pool.server_prefix !== null) return null;
  if (pool.label_problems.length > 0) {
    return `Its agentLabels name no servers (${pool.label_problems.join("; ")}): the workflow refuses a pool draw into it. Set them on the InfraEnv, or install servers by name.`;
  }
  return "Wingman could not read this InfraEnv's agentLabels (live status off, or the MCE unreadable), so it does not know its servers' names. The workflow checks the server you name.";
}
