/**
 * day1's route for the Server Scan area's Architecture page
 * (docs/notes/2026-11-13-server-scan-area-api.md §11, ADR-0048's 3.28.0
 * amendment): one of server-scan's diagrams, read through day1 from its UI.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { retryUnlessProblem } from "@/lib/api/server-scan";
import type { DiagramAnswer } from "@/types/server-scan-architecture";

/**
 * As server-scan's page, which reads its static file once per frame load:
 * a diagram changes only when server-scan is released, so one read a
 * session is enough. Never kept in localStorage (`components/layout/providers.tsx`):
 * about 0.7 MB each.
 */
const DIAGRAM_STALE_MS = 30 * 60_000;

const diagramKey = (slug: string) => ["server-scan", "architecture", slug] as const;

/** One of server-scan's diagrams, the page its UI serves. */
export function useServerScanDiagram(slug: string) {
  return useQuery<DiagramAnswer>({
    queryKey: diagramKey(slug),
    queryFn: () => api.get<DiagramAnswer>(`/api/day1/server-scan/architecture/${encodeURIComponent(slug)}`),
    staleTime: DIAGRAM_STALE_MS,
    retry: retryUnlessProblem,
  });
}
