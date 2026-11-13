"use client";

import { useCallback, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { parseView, viewHref, type SegmentsView } from "@/lib/segments/view";

/**
 * The page's view, read from and written to the URL. A change replaces the
 * history entry (Next keeps `useSearchParams` in step with
 * `history.replaceState`), so filtering costs no navigation and no request.
 */
export function useSegmentsView(): [SegmentsView, (next: SegmentsView) => void] {
  const params = useSearchParams();
  const view = useMemo(() => parseView(params), [params]);
  const setView = useCallback((next: SegmentsView) => {
    const href = viewHref(next);
    if (href !== `${window.location.pathname}${window.location.search}`) window.history.replaceState(null, "", href);
  }, []);
  return [view, setView];
}
