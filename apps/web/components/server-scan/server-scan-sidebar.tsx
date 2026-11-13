"use client";

import { usePathname } from "next/navigation";
import { AreaNav } from "@/components/layout/area-nav";
import { serverScanSidebar } from "@/lib/server-scan/sidebar";

/** The Server Scan area's sidebar: server-scan's pages that Wingman has built (ADR-0048). */
export function ServerScanSidebar() {
  return <AreaNav label="Server Scan" sections={serverScanSidebar(usePathname())} />;
}
