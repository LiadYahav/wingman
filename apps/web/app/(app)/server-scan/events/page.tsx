import { Suspense } from "react";
import { EventsPage } from "@/components/server-scan/events/events-page";

/**
 * The Server Scan area's Events page (ADR-0048's 3.31.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §14): server-scan's audit
 * trail of the fleet, filtered and paged as server-scan's, for Wingman's
 * admins. The filters are in the URL, so the page renders below a Suspense
 * boundary.
 */
export default function Page() {
  return (
    <Suspense>
      <EventsPage />
    </Suspense>
  );
}
