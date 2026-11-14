import { RulesPage } from "@/components/server-scan/rules-page";

/**
 * The Server Scan area's Rules & Policies page (ADR-0048's 3.30.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §13): what server-scan runs,
 * its classification rules and health policies, read only, for Wingman's admins.
 */
export default function Page() {
  return <RulesPage />;
}
