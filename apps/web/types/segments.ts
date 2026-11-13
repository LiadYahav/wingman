/**
 * The Segments area: day1's typed view of segments-manager's open reads
 * (docs/notes/2026-11-13-segments-area-api.md, ADR-0047). Admins only;
 * `501 FEATURE_DISABLED` when segments-manager is not configured.
 */

/** segments-manager's types, in its order. Only an Allocated segment has one. */
export const SEGMENT_TYPES = ["HC", "MCE", "INVENTORY", "PXE", "UPI", "HUB"] as const;

// ── GET /api/day1/segments/sites ──────────────────────────────────────────────

export interface SegmentSites {
  /** segments-manager's sites, in its order; a site may have no segments yet. */
  sites: string[];
}

// ── GET /api/day1/segments/stats ──────────────────────────────────────────────

export interface SegmentTypeCount {
  type: string;
  /** Allocated segments of this type: a count, never "x of y". */
  allocated: number;
}

export interface SiteSegmentStats {
  site: string;
  total_segments: number;
  allocated: number;
  by_type: SegmentTypeCount[];
}

export interface SegmentStats {
  /** One per site of `/sites`, in that order. */
  sites: SiteSegmentStats[];
}

// ── GET /api/day1/segments ────────────────────────────────────────────────────

/** Where a holder's cluster file is in the day1 repo. */
export interface Day1Location {
  site: string;
  mce: string;
}

export interface SegmentHolder {
  name: string;
  /** `null` for any holder without exactly one cluster file in day1 (an MCE, a UPI cluster, an unknown name). */
  day1: Day1Location | null;
}

export interface Segment {
  /** The CIDR: the key, never null. */
  segment: string;
  site: string | null;
  vlan_id: number | null;
  epg_name: string | null;
  dhcp: boolean | null;
  /** `null` on an old record, shown as Available. */
  status: string | null;
  type: string | null;
  /** One name, a list for a shared `UPI` segment, `null` while Available. */
  cluster_name: string | string[] | null;
  allocated_at: string | null;
  holders: SegmentHolder[];
}

export interface SegmentList {
  segments: Segment[];
  /** Records segments-manager sent that day1 could not read, one sentence each. */
  unreadable: string[];
  /** Why day1's cluster files could not be read: holders are then unlinked. */
  clusters_error: string | null;
  /** `true` when read from segments-manager's database just now (`fresh=true`). */
  fresh: boolean;
}
