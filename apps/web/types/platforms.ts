/**
 * The systems beside Wingman in an admin's Infrastructure sidebar:
 * segments-manager and server-scan (ADR-0066, ADR-0067). Admins only.
 */

// ── GET /api/day1/platforms ───────────────────────────────────────────────────

/** One system day1 is configured for. */
export interface Platform {
  id: "segments" | "server-scan";
  /** Its own name, the link's label: "Segments Manager", "Server Scan". */
  name: string;
  /** Its own UI, for the browser (`*_UI_URL`, else its API's URL). */
  url: string;
}

export interface Platforms {
  /** In the sidebar's order; a system day1 is not configured for is not listed. */
  platforms: Platform[];
}
