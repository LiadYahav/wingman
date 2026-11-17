/**
 * The Server Scan area's Servers page: server-scan's fleet rows, which day1
 * passes through typed and in their own shape
 * (docs/notes/2026-11-13-server-scan-area-api.md §8, ADR-0048's 3.23.0
 * amendment). Admins only.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/types/server.ts`. As there, `X | null`
 * means "always sent, may be null".
 */

import type { HealthSeverity, InstallationType, OpenShiftState, Vendor } from "./server-scan";

/** A server's maintenance, as a row carries it. */
export interface MaintenanceState {
  enabled: boolean;
  reason: string | null;
  /** Who set it: a person, or a token (`api-token-admin`); null when unrecorded. */
  created_by?: string | null;
}

/**
 * The install lock on a row (server-scan's ADR-0035). `held` is judged by
 * server-scan when the rows were read, so an expired lock reads as free; one
 * not held has every other field null.
 */
export interface ReservationState {
  held: boolean;
  holder: string | null;
  /** The MCE the install is headed for: the field worth showing. */
  mce_cluster: string | null;
  infra_env: string | null;
  expires_at: string | null;
}

/** One server: `GET /api/day1/server-scan/servers` (server-scan's `GET /api/v1/servers/rows`). */
export interface ServerRow {
  id: string;
  name: string;
  vendor: Vendor;
  model: string | null;
  /** The code in the name, or null when the name carries no site (Unassigned). */
  site_id: string | null;
  /** The collector that reads it (`OPENMANAGE`, `INTERSIGHT`, …). */
  source_provider: string | null;
  installation_type: InstallationType;
  health: HealthSeverity;
  maintenance: MaintenanceState;
  reservation: ReservationState;
  openshift_state: OpenShiftState;
  cluster_name: string | null;
  mce_name: string | null;
  /** Set only when OpenShift reports another hostname than `name` (a rename after install). */
  openshift_reported_name: string | null;
  /** The other cluster or MCE claiming the same server; null when uncontested. */
  contested_with: string | null;
  profile_template_name: string | null;
  last_seen_at: string | null;
  /** Unseen for longer than server-scan's staleness window, or never. */
  stale: boolean;
  reachable: boolean;
  serial: string | null;
  bmc_host: string | null;
  macs: string[];
}

/** day1's answer: server-scan's rows, and whether the maintenance toggle works here (§8.4). */
export interface ServerRowsAnswer {
  items: ServerRow[];
  /** When the inventory last changed, as server-scan says. */
  generated_at: string | null;
  maintenance_available: boolean;
  /** Why the toggle does not work, in one line; null when it does. */
  maintenance_detail: string | null;
}

/** The answer to a maintenance change: the server's new maintenance (§8.3). */
export interface MaintenanceAnswer {
  id: string;
  name: string;
  maintenance: MaintenanceState;
}

/** `PUT …/maintenance`: both optional, as server-scan's API takes them. */
export interface MaintenanceStart {
  reason: string | null;
  /** ISO 8601 date and time. */
  expected_end: string | null;
}
