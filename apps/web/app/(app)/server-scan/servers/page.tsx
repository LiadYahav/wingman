import { Suspense } from "react";
import { ServersPage } from "@/components/server-scan/servers-page";

/**
 * The Server Scan area's Servers page (ADR-0048's 3.23.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §8): server-scan's fleet,
 * one row per server, for Wingman's admins. The view lives in the URL, so
 * the page renders below a Suspense boundary.
 */
export default function Page() {
  return (
    <Suspense>
      <ServersPage />
    </Suspense>
  );
}
