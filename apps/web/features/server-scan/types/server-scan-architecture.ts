/**
 * The Server Scan area's Architecture page: one of server-scan's diagrams,
 * the page its UI serves, passed through day1
 * (docs/notes/2026-11-13-server-scan-area-api.md §11, ADR-0048's 3.28.0
 * amendment). Admins only.
 */

/** `GET /api/day1/server-scan/architecture/{slug}`. */
export interface DiagramAnswer {
  slug: string;
  /** server-scan's page as served: shown only in a sandboxed frame, never in Wingman's page. */
  html: string;
}
