import { useSegmentsArea } from "@/features/segments/api/segments";
import { useServerScanArea } from "@/features/server-scan/api/server-scan";
import type { AreaAccess } from "@/lib/areas";

/** Which areas this person has: an admin, with each system configured (ADR-0047, ADR-0048). */
export function useAreaAccess(): AreaAccess {
  return { segments: useSegmentsArea(), "server-scan": useServerScanArea() };
}
