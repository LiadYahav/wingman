/**
 * The Segments area: day1's typed view of segments-manager's open reads
 * (docs/notes/2026-11-13-segments-area-api.md, ADR-0047). Admins only;
 * `501 FEATURE_DISABLED` when segments-manager is not configured.
 */

// ── GET /api/day1/segments/sites ──────────────────────────────────────────────

export interface SegmentSites {
  /** segments-manager's sites, in its order; a site may have no segments yet. */
  sites: string[];
}
