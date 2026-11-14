import { ConfsPage } from "@/components/server-scan/confs-page";

/**
 * The Server Scan area's Confs page (ADR-0048's 3.29.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §10): server-scan's hardware
 * catalog, one row per server configuration, read only, for Wingman's admins.
 */
export default function Page() {
  return <ConfsPage />;
}
