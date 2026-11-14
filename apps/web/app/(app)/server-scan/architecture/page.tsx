import { Suspense } from "react";
import { ArchitecturePage } from "@/components/server-scan/architecture-page";

/**
 * The Server Scan area's Architecture page (ADR-0048's 3.28.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §11): server-scan's
 * diagrams, as its UI serves them, for Wingman's admins. The diagram shown
 * lives in the URL, so the page renders below a Suspense boundary.
 */
export default function Page() {
  return (
    <Suspense>
      <ArchitecturePage />
    </Suspense>
  );
}
