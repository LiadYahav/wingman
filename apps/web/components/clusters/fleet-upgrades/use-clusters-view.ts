"use client";

import { useSyncExternalStore } from "react";
import { clustersViewOf, UPGRADES_HASH, type ClustersView } from "@/lib/fleet-upgrades";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("hashchange", onChange);
  window.addEventListener("popstate", onChange);
  return () => {
    window.removeEventListener("hashchange", onChange);
    window.removeEventListener("popstate", onChange);
  };
}

/**
 * The Clusters page's view, from the URL's hash (`/clusters#upgrades`), so
 * Back from a cluster returns to it and the link can be shared. A hash, not
 * a query: the page needs no Suspense boundary for it.
 */
export function useClustersView(): ClustersView {
  return clustersViewOf(useSyncExternalStore(subscribe, () => window.location.hash, () => ""));
}

/** Show `view`: a new history entry, so Back returns to the other one. */
export function showClustersView(view: ClustersView): void {
  const { pathname, search } = window.location;
  window.history.pushState(null, "", `${pathname}${search}${view === "upgrades" ? UPGRADES_HASH : ""}`);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}
