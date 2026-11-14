import { Suspense } from "react";
import { ServerPage } from "@/components/server-scan/server/server-page";

/**
 * The Server Scan area's server page (ADR-0048's 3.25.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §9): one server's record, its
 * five tabs as server-scan's, for Wingman's admins. The tab is in the URL, so
 * the page renders below a Suspense boundary.
 */
export default function Page() {
  return (
    <Suspense>
      <ServerPage />
    </Suspense>
  );
}
