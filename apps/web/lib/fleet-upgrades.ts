/**
 * How the fleet's upgrade runs read on the Clusters page (ADR-0055's
 * amendment), as pure functions. The words are the workflow's: a phase is
 * only made readable, `waiting_for` only shortened (its whole text is the
 * tooltip). The decisions stay on the cluster page.
 */

import { clusterQuery } from "@/lib/clusters";
import type { FleetUpgrade } from "@/types";

export type FleetTone = "open" | "done" | "stopped" | "failed";

/** Whether the upgrade is still going on. */
export const isOpenUpgrade = (run: FleetUpgrade): boolean => run.status === "running";

/** The open upgrades, by cluster: the clusters list's "Upgrading" badges. */
export function openByCluster(runs: readonly FleetUpgrade[]): Map<string, FleetUpgrade> {
  return new Map(runs.filter(isOpenUpgrade).map((run) => [run.cluster, run]));
}

/**
 * The word to show for the run's state, still the workflow's (humanize it to
 * show): `paused` or its phase while open (`null` when not read yet), how it
 * ended once closed (its outcome, else the orchestrator's status).
 */
export function stateWord(run: FleetUpgrade): string | null {
  if (isOpenUpgrade(run)) return run.paused ? "paused" : run.phase;
  return run.outcome ?? run.status;
}

/** The status chip's colour family. */
export function fleetTone(run: FleetUpgrade): FleetTone {
  if (isOpenUpgrade(run)) return "open";
  if (run.outcome === "done") return "done";
  if (run.outcome === "cancelled" || run.outcome === "aborted") return "stopped";
  return "failed";
}

/** At most `max` characters of `text`, cut at a word, with an ellipsis when cut. */
export function brief(text: string, max = 90): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= max) return flat;
  const cut = flat.slice(0, max - 1);
  const space = cut.lastIndexOf(" ");
  return `${(space > max / 2 ? cut.slice(0, space) : cut).trimEnd()}…`;
}

/** The cluster's page, where its Upgrade panel shows the run and its decisions. */
export function upgradeHref(run: FleetUpgrade): string {
  return `/clusters/${encodeURIComponent(run.cluster)}${clusterQuery(run.site ?? "", run.mce ?? "")}`;
}

/** The Clusters page's two views; the URL's `#upgrades` picks the second. */
export type ClustersView = "clusters" | "upgrades";

export const UPGRADES_HASH = "#upgrades";

/** The view a URL hash asks for. */
export const clustersViewOf = (hash: string): ClustersView => (hash === UPGRADES_HASH ? "upgrades" : "clusters");
