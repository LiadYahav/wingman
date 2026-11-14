import { ClaudePage } from "@/components/server-scan/claude/claude-page";

/**
 * The Server Scan area's Claude page (ADR-0048's 3.29.0 amendment,
 * docs/notes/2026-11-13-server-scan-area-api.md §12): server-scan's Claude
 * Code skill, its download and its MCP command, for Wingman's admins.
 */
export default function Page() {
  return <ClaudePage />;
}
