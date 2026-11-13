/**
 * The clusters list's upgrades (ADR-0055's amendments), as pure functions:
 * each row's state, the list's Upgrade filter in the URL, and the fleet's
 * runs kept current after a start. The words are the workflow's: a phase is
 * only made readable. The plan and the decisions stay on the cluster page.
 */

import type { FleetUpgrade, UpgradeRun } from "@/types";

/** Whether the upgrade is still going on. */
const isOpenUpgrade = (run: FleetUpgrade): boolean => run.status === "running";

/** The open upgrades, by cluster. */
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

/**
 * A row's upgrade: its open run, else the newer release its MCE offers
 * (day1's `upgrade_available`, a suggestion), else nothing: up to date rows
 * stay quiet. An open run wins: the cluster has one upgrade at a time.
 */
export type RowUpgrade = { kind: "upgrading"; run: FleetUpgrade } | { kind: "available"; version: string } | null;

export function rowUpgrade(
  cluster: { name: string; upgrade_available: string | null },
  open: ReadonlyMap<string, FleetUpgrade>
): RowUpgrade {
  const run = open.get(cluster.name);
  if (run) return { kind: "upgrading", run };
  return cluster.upgrade_available ? { kind: "available", version: cluster.upgrade_available } : null;
}

// ── The list's Upgrade filter, kept in the URL (`?upgrade=`) ────────────────

export type UpgradeFilter = "all" | "available" | "upgrading";

export const UPGRADE_FILTERS: readonly { value: UpgradeFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "available", label: "Upgrade available" },
  { value: "upgrading", label: "Upgrading" },
];

const UPGRADE_PARAM = "upgrade";

/** The filter a URL's query asks for; anything else is All. */
export function upgradeFilterOf(search: string): UpgradeFilter {
  const value = new URLSearchParams(search).get(UPGRADE_PARAM);
  return value === "available" || value === "upgrading" ? value : "all";
}

/** The URL showing `filter`, every other part of `url` kept. */
export function withUpgradeFilter(url: { pathname: string; search: string; hash: string }, filter: UpgradeFilter): string {
  const params = new URLSearchParams(url.search);
  if (filter === "all") params.delete(UPGRADE_PARAM);
  else params.set(UPGRADE_PARAM, filter);
  const query = params.toString();
  return `${url.pathname}${query ? `?${query}` : ""}${url.hash}`;
}

/** Whether a row with `upgrade` is shown under `filter`. */
export function matchesUpgradeFilter(upgrade: RowUpgrade, filter: UpgradeFilter): boolean {
  return filter === "all" || upgrade?.kind === filter;
}

/** How many rows each filter shows. */
export function countUpgrades(upgrades: readonly RowUpgrade[]): Record<Exclude<UpgradeFilter, "all">, number> {
  return {
    available: upgrades.filter((u) => u?.kind === "available").length,
    upgrading: upgrades.filter((u) => u?.kind === "upgrading").length,
  };
}

// ── After a start ───────────────────────────────────────────────────────────

/**
 * The fleet's runs with a run just started on its cluster, in place of that
 * cluster's previous one: the list shows "Upgrading" at once, until the next
 * read (day1 dropped its cached list on the start). Where day1 has the file
 * is kept from the previous row.
 */
export function withStartedRun(runs: readonly FleetUpgrade[], run: UpgradeRun, startedAt: string): FleetUpgrade[] {
  const previous = runs.find((r) => r.cluster === run.cluster);
  const started: FleetUpgrade = {
    workflow_id: run.workflow_id,
    cluster: run.cluster,
    site: previous?.site ?? null,
    mce: previous?.mce ?? run.mce,
    status: run.status,
    started_at: startedAt,
    closed_at: null,
    phase: run.phase,
    waiting_for: run.waiting_for,
    paused: run.paused,
    outcome: run.outcome,
  };
  return [started, ...runs.filter((r) => r.cluster !== run.cluster)];
}
