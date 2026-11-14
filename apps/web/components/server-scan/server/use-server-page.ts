"use client";

import { useCallback, useSyncExternalStore } from "react";
import { useSearchParams } from "next/navigation";
import { SERVERS_HREF, backHref, parseTab, type ServerTab } from "@/lib/server-scan/server-page";

/**
 * The server page's state that lives outside React: its tab, in the URL
 * (`?tab=`), and the Servers view "← Servers" returns to, in the browser's
 * session (server-scan keeps that in its router's state). Storage can be
 * missing or refuse (a private window): then the link is the unfiltered list.
 */

const SERVERS_VIEW_KEY = "wingman-server-scan-servers-view";

/** Remember the Servers view a server's page is opened from (its path and filters). */
export function rememberServersView(href: string) {
  try {
    sessionStorage.setItem(SERVERS_VIEW_KEY, href);
  } catch {
    /* storage unavailable: "← Servers" opens the unfiltered list */
  }
}

function storedServersView(): string | null {
  try {
    return sessionStorage.getItem(SERVERS_VIEW_KEY);
  } catch {
    return null;
  }
}

const noChanges = () => () => {};

/** Where "← Servers" goes; the unfiltered list on the server, before the browser's session is read. */
export function useServersBackHref(): string {
  return useSyncExternalStore(noChanges, () => backHref(storedServersView()), () => SERVERS_HREF);
}

/**
 * The tab, read from the URL and written to it. A change replaces the
 * history entry (Next keeps `useSearchParams` in step with
 * `history.replaceState`), so switching tabs costs no navigation and Back
 * leaves the page.
 */
export function useServerTab(): [ServerTab, (tab: ServerTab) => void] {
  const params = useSearchParams();
  const tab = parseTab(params.get("tab"));
  const setTab = useCallback((next: ServerTab) => {
    const href = next === "overview" ? window.location.pathname : `${window.location.pathname}?tab=${next}`;
    if (href !== `${window.location.pathname}${window.location.search}`) window.history.replaceState(null, "", href);
  }, []);
  return [tab, setTab];
}
