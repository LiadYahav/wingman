import { Suspense } from "react";
import { SegmentsPage } from "@/components/segments/segments-page";

/**
 * The Segments area (ADR-0047, docs/notes/2026-11-13-segments-area-api.md):
 * segments-manager's segments, read only, for Wingman's admins. The view
 * lives in the URL, so the page renders below a Suspense boundary.
 */
export default function Page() {
  return (
    <Suspense>
      <SegmentsPage />
    </Suspense>
  );
}
