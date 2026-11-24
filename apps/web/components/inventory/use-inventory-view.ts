"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";
import {
  cleanNames,
  parseStoredView,
  readStoredView,
  resolveView,
  serializeView,
  viewFromSearch,
  withView,
  writeStoredView,
  type InventoryView,
  type ResolvedView,
} from "@/lib/inventory/view";
import type { MceInventory } from "@/types/inventory";

/** Whoever reads the view, told when it is set here: `replaceState` fires no event, and `storage` only fires in other tabs. */
const listeners = new Set<() => void>();

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  window.addEventListener("popstate", onChange);
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("popstate", onChange);
    window.removeEventListener("storage", onChange);
  };
}

const browserStorage = (): Storage | undefined => {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
};

const stored = () => readStoredView(browserStorage());

export interface InventoryViewState extends ResolvedView {
  /** Shows `mce`; the InfraEnvs picked stay. */
  setMce: (mce: string) => void;
  setInfraEnvs: (infraEnvs: readonly string[]) => void;
}

/**
 * The MCE Inventory Management shows and the InfraEnvs picked (ADR-0057's
 * 2026-11-24 amendment): from the URL, else this browser's last choice, else
 * the first MCE with something to show. A choice replaces the history entry,
 * as the clusters list's filters do, and is kept for the next visit. Read
 * without `useSearchParams`, so the page needs no Suspense boundary.
 */
export function useInventoryView(mces: readonly MceInventory[] | undefined): InventoryViewState {
  const search = useSyncExternalStore(subscribe, () => window.location.search, () => "");
  const kept = useSyncExternalStore(subscribe, stored, () => null);
  const view = useMemo(() => resolveView(viewFromSearch(search), parseStoredView(kept), mces ?? []), [search, kept, mces]);

  const show = useCallback((next: InventoryView) => {
    window.history.replaceState(null, "", withView(window.location, next));
    writeStoredView(browserStorage(), serializeView(next));
    listeners.forEach((listener) => listener());
  }, []);
  const current = view.mce?.mce ?? null;
  const setMce = useCallback((mce: string) => show({ mce, infraEnvs: view.infraEnvs }), [show, view.infraEnvs]);
  const setInfraEnvs = useCallback(
    (infraEnvs: readonly string[]) => show({ mce: current, infraEnvs: cleanNames(infraEnvs) }),
    [show, current]
  );
  return { ...view, setMce, setInfraEnvs };
}
