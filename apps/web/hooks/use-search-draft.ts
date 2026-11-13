"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useDebounced } from "@/hooks/use-debounced";

/**
 * The search box's text, and its way into the URL: `commit(q)` once typing
 * pauses for `ms` (250 ms by default), or at once with `flush()`. The URL never writes back
 * into the box: a caller that changes `q` itself (Clear filters) sets the
 * draft too.
 */
export function useSearchDraft(q: string, commit: (q: string) => void, ms = 250) {
  const [draft, setDraft] = useState(q);
  const settled = useDebounced(draft, ms);
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
