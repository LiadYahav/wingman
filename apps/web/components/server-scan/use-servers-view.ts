"use client";

import { useCallback, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { parseServersView, serversHref, type ServersView } from "@/lib/server-scan/servers-view";

/**
 * The Servers page's view, read from and written to the URL under
 * server-scan's parameter names. A change replaces the history entry (Next
 * keeps `useSearchParams` in step with `history.replaceState`), so filtering
 * costs no navigation and no request.
 */
export function useServersView(): [ServersView, (next: ServersView) => void] {
  const params = useSearchParams();
  const view = useMemo(() => parseServersView(params), [params]);
  const setView = useCallback((next: ServersView) => {
    const href = serversHref(next);
    if (href !== `${window.location.pathname}${window.location.search}`) window.history.replaceState(null, "", href);
  }, []);
  return [view, setView];
}
