"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDebounced } from "@/hooks/use-debounced";
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

/**
 * The search box's text, and its way into the URL: `commit(q)` once typing
 * pauses for 250 ms, or at once with `flush()`. The URL never writes back
 * into the box: a caller that changes `q` itself (Clear filters) sets the
 * draft too.
 */
export function useSearchDraft(q: string, commit: (q: string) => void) {
  const [draft, setDraft] = useState(q);
  const settled = useDebounced(draft, 250);
  const latest = useRef({ q, commit, draft });
  useEffect(() => {
    latest.current = { q, commit, draft };
  });
  useEffect(() => {
    if (settled !== latest.current.q) latest.current.commit(settled);
  }, [settled]);
  const flush = useCallback(() => {
    if (latest.current.draft !== latest.current.q) latest.current.commit(latest.current.draft);
  }, []);
  return { draft, setDraft, flush };
}
