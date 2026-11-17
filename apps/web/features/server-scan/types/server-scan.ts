/**
 * The Server Scan area: server-scan's own answers, which day1 passes through
 * typed and in their own shape (docs/notes/2026-11-13-server-scan-area-api.md,
 * ADR-0048). Admins only; `501 FEATURE_DISABLED` when server-scan is not
 * configured.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/types/server.ts` and
 * `frontend/src/api/sites.ts`. A value server-scan adds later (a vendor, a
 * severity) still arrives: day1 keeps every key it sends.
 */

export type Vendor = "dell" | "cisco" | "hp" | "standalone" | "kubevirt";

/** A server's overall health; `UNKNOWN` is "no policy has said anything yet", not a verdict. */
export type HealthSeverity = "UNKNOWN" | "HEALTHY" | "WARNING" | "MAJOR" | "CRITICAL";

/** What the server was named to be: server-scan's classification of its hostname. */
export type InstallationType = "HOSTED_CLUSTER" | "MCE" | "UPI" | "UNCLASSIFIED";

/** Whether a cluster or an MCE uses it: no one, a cluster's node, or an MCE's Agent in no cluster yet. */
export type OpenShiftState = "AVAILABLE" | "INSTALLED" | "INSTALLED_TO_INVENTORY";

// ── GET /api/day1/server-scan/sites (server-scan's GET /api/v1/sites) ─────────

export interface VendorCount {
  vendor: Vendor | (string & {});
  count: number;
}

/** The counts of one slice of the fleet: a site, the fleet, or one type or state within them. */
export interface Breakdown {
  total: number;
  /** Every vendor, zeroes included, in server-scan's order. */
  by_vendor: VendorCount[];
  /** Every severity, zeroes included. */
  by_health: Partial<Record<HealthSeverity, number>>;
  in_maintenance: number;
}

/** The fleet, summed by server-scan (never in the browser), sliced by type and by state. */
export interface FleetSummary extends Breakdown {
  by_installation_type: Partial<Record<InstallationType, Breakdown>>;
  by_openshift_state: Partial<Record<OpenShiftState, Breakdown>>;
}

/** One configured site, or `unassigned` (servers whose name carries no site). */
export interface SiteStats extends FleetSummary {
  /** The code in server names (`tlv`, `bat-yam`), or `unassigned`. */
  site_id: string;
  /** What the UI shows (`Tel Aviv`). */
  name: string;
}

export interface SiteStatsList {
  /** Every configured site in server-scan's order, then `unassigned`. */
  items: SiteStats[];
  fleet: FleetSummary;
}
