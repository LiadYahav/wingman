import { useSegmentsArea } from "@/lib/api/segments";
import { useServerScanArea } from "@/lib/api/server-scan";
import type { AreaAccess } from "@/lib/areas";

/** Which areas this person has: an admin, with each system configured (ADR-0047, ADR-0048). */
export function useAreaAccess(): AreaAccess {
  return { segments: useSegmentsArea(), "server-scan": useServerScanArea() };
}
