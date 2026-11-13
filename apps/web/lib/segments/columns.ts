/**
 * The Segments table's columns: segments-manager's own, with its words
 * (docs/notes/2026-11-13-segments-area-api.md §5), and how each shows a
 * segment as text, for the search, the sort and the CSV.
 */

import type { Segment } from "@/types/segments";

export const COLUMN_IDS = ["type", "site", "vlan_id", "epg_name", "segment", "dhcp", "cluster", "status"] as const;
export type ColumnId = (typeof COLUMN_IDS)[number];

/** The original's headers, word for word. */
export const COLUMN_LABELS: Record<ColumnId, string> = {
  type: "Type",
  site: "Site",
  vlan_id: "VLAN ID",
  epg_name: "EPG Name",
  segment: "Network Segment",
  dhcp: "DHCP",
  cluster: "Cluster",
  status: "Status",
};

export const isColumnId = (value: string): value is ColumnId => (COLUMN_IDS as readonly string[]).includes(value);

/** The holders' names, as the original shows them: a shared UPI segment's joined with ", ". */
function clusterLabel(segment: Segment): string {
  return segment.holders.map((holder) => holder.name).join(", ");
}

/** A record without a status is shown as Available, as segments-manager's UI does. */
export function statusLabel(segment: Segment): string {
  return segment.status || "Available";
}

export function isAllocated(segment: Segment): boolean {
  return statusLabel(segment).toLowerCase() === "allocated";
}

/** `On`, `Off`, or empty when an old record has no value. */
export function dhcpLabel(segment: Segment): string {
  if (segment.dhcp === null) return "";
  return segment.dhcp ? "On" : "Off";
}

/** What a cell says, as plain text (empty for nothing). */
export function cellText(segment: Segment, column: ColumnId): string {
  switch (column) {
    case "type":
      return segment.type ?? "";
    case "site":
      return segment.site ?? "";
    case "vlan_id":
      return segment.vlan_id === null ? "" : String(segment.vlan_id);
    case "epg_name":
      return segment.epg_name ?? "";
    case "segment":
      return segment.segment;
    case "dhcp":
      return dhcpLabel(segment);
    case "cluster":
      return clusterLabel(segment);
    case "status":
      return statusLabel(segment);
  }
}
