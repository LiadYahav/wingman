import { SitesPage } from "@/components/server-scan/sites-page";

/**
 * The Server Scan area's home, server-scan's Sites page (ADR-0048,
 * docs/notes/2026-11-13-server-scan-area-api.md): a card for the fleet and
 * for each site, for Wingman's admins. The area's other pages come one by one.
 */
export default function Page() {
  return <SitesPage />;
}
