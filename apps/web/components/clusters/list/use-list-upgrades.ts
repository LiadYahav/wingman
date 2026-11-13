"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";
import { isApiError } from "@/lib/api-client";
import { useFleetUpgrades } from "@/lib/api/upgrades";
import {
  countUpgrades,
  matchesUpgradeFilter,
  openByCluster,
  rowUpgrade,
  upgradeFilterOf,
  withUpgradeFilter,
  type RowUpgrade,
  type UpgradeFilter,
} from "@/lib/fleet-upgrades";
import type { ClusterStatus } from "@/types";

/** Whoever reads the filter, told when it is set here: `replaceState` fires no event. */
const listeners = new Set<() => void>();

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  window.addEventListener("popstate", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("popstate", onChange);
  };
}

/**
 * The Upgrade filter, from the URL's `?upgrade=`: Back from a cluster returns
 * to the filtered list, and the link can be shared. A change replaces the
 * history entry, as the Segments page's filters do. Read without
 * `useSearchParams`, so the page needs no Suspense boundary.
 */
function useUpgradeFilter(): [UpgradeFilter, (next: UpgradeFilter) => void] {
  const filter = upgradeFilterOf(useSyncExternalStore(subscribe, () => window.location.search, () => ""));
  const setFilter = useCallback((next: UpgradeFilter) => {
    window.history.replaceState(null, "", withUpgradeFilter(window.location, next));
    listeners.forEach((listener) => listener());
  }, []);
  return [filter, setFilter];
}

/** What the clusters list shows of upgrades. */
export interface ListUpgrades {
  /** Upgrades are on (DAY1_UPGRADES): the Upgrade filter shows. Off, the list shows nothing of them. */
  on: boolean;
  /** Each row's state: upgrading, an upgrade available, or nothing. */
  stateOf: (cluster: ClusterStatus) => RowUpgrade;
  counts: ReturnType<typeof countUpgrades>;
  /** The fleet's runs could not be read: no row shows "Upgrading", and the filter says why. */
  error: unknown;
  /** All while upgrades are off, whatever the URL says. */
  filter: UpgradeFilter;
  /** Whether a row is shown under the filter. */
  matches: (cluster: ClusterStatus) => boolean;
  setFilter: (next: UpgradeFilter) => void;
}

/**
 * The clusters list's upgrades (ADR-0055's amendments): each row's open run,
 * from the one fleet query every row shares, or the newer release its MCE
 * offers, which day1 sends with the list (`upgrade_available`, only while
 * upgrades are on). Nothing is read per row.
 */
export function useListUpgrades(clusters: readonly ClusterStatus[] | undefined): ListUpgrades {
  const fleet = useFleetUpgrades();
  const [urlFilter, setFilter] = useUpgradeFilter();
  const runs = fleet.data?.state === "on" ? fleet.data.runs : null;
  const open = useMemo(() => openByCluster(runs ?? []), [runs]);
  const stateOf = useCallback((cluster: ClusterStatus) => rowUpgrade(cluster, open), [open]);
  const counts = useMemo(() => countUpgrades((clusters ?? []).map(stateOf)), [clusters, stateOf]);
  const failed = fleet.error && !isApiError(fleet.error, "FEATURE_DISABLED") ? fleet.error : null;
  const on = runs !== null || failed !== null || (clusters ?? []).some((c) => c.upgrade_available);
  const filter = on ? urlFilter : "all";
  const matches = useCallback((cluster: ClusterStatus) => matchesUpgradeFilter(stateOf(cluster), filter), [stateOf, filter]);
  return { on, stateOf, counts, error: failed, filter, matches, setFilter };
}
