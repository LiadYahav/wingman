"use client";

import { Suspense, type ComponentType } from "react";
import { SegmentsSidebar } from "@/components/segments/segments-sidebar";
import { ServerScanSidebar } from "@/components/server-scan/server-scan-sidebar";
import type { AreaId } from "@/lib/areas";
import { SidebarNav } from "./sidebar-nav";

/**
 * Each area's sidebar (ADR-0047's amendment). Wingman's is its own list
 * (sidebar-nav.tsx, unchanged); every other area's is built from data
 * (`lib/areas.ts`'s sections, rendered by `AreaNav`).
 */
const SIDEBARS: Record<AreaId, ComponentType> = {
  wingman: SidebarNav,
  segments: SegmentsSidebar,
  "server-scan": ServerScanSidebar,
};

/** The area's sidebar; below Suspense because an area's may read the URL. */
export function AreaSidebar({ area }: { area: AreaId }) {
  const Sidebar = SIDEBARS[area];
  return (
    <Suspense>
      <Sidebar />
    </Suspense>
  );
}
