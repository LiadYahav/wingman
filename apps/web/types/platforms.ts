/**
 * The systems beside Wingman in an admin's top bar: segments-manager and
 * server-scan (ADR-0047 and ADR-0048's 2026-11-23 amendments). Admins only.
 */

// ── GET /api/day1/platforms ───────────────────────────────────────────────────

/** One system day1 is configured for. */
export interface Platform {
  /** The web's area id, also when the area is off. */
  id: "segments" | "server-scan";
  /** Its own name: "Segments Manager", "Server Scan". */
  name: string;
  /** Its own UI, for the browser (`*_UI_URL`, else its API's URL). */
  url: string;
  /** Whether Wingman's area for it is on (`DAY1_SEGMENTS_AREA`, `DAY1_SERVER_SCAN_AREA`). */
  area: boolean;
}

export interface Platforms {
  /** In the top bar's order; a system day1 is not configured for is not listed. */
  platforms: Platform[];
}
