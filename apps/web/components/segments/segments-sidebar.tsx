"use client";

import { useSearchParams } from "next/navigation";
import { AreaNav } from "@/components/layout/area-nav";
import { useSegmentStats } from "@/lib/api/segments";
import { segmentsSidebar, type SitesState } from "@/lib/segments/sidebar";
import { parseView } from "@/lib/segments/view";

/**
 * The Segments area's sidebar: the page's options as links that set its URL
 * filters, and every site with used out of total, from the same stats query
 * (and cache) as the page's cards. Reads the URL, so it renders below a
 * Suspense boundary.
 */
export function SegmentsSidebar() {
  const params = useSearchParams();
  const stats = useSegmentStats();
  const sites: SitesState = stats.data ? { sites: stats.data.sites } : stats.isError ? "error" : "loading";
  return <AreaNav label="Segments" sections={segmentsSidebar(parseView(params), sites)} />;
}
