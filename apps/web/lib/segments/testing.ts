/** Segments for the unit tests (made up), in day1's shape (docs/notes/2026-11-13-segments-area-api.md §3). */

import type { Segment } from "@/types/segments";

/** A segment; `holders` follows `cluster_name` unless given. */
export function segment(overrides: Partial<Segment> = {}): Segment {
  const base: Segment = {
    segment: "10.20.42.0/24",
    site: "site1",
    vlan_id: 1408,
    epg_name: "EPG_site1_HC_1408",
    dhcp: true,
    status: "Allocated",
    type: "HC",
    cluster_name: "ocp4-prep-eyal-site1",
    allocated_at: "2026-10-02T09:12:40+00:00",
    holders: [],
    mismatches: [],
  };
  const merged = { ...base, ...overrides };
  if (overrides.holders) return merged;
  const names = merged.cluster_name === null ? [] : Array.isArray(merged.cluster_name) ? merged.cluster_name : [merged.cluster_name];
  return { ...merged, holders: names.map((name) => ({ name, day1: null })) };
}

export const free = (overrides: Partial<Segment> = {}): Segment =>
  segment({ status: "Available", type: null, cluster_name: null, ...overrides });
