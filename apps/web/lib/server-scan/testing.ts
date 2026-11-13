/** Servers for the unit tests (made up), in server-scan's row shape (docs/notes/2026-11-13-server-scan-area-api.md §8.3). */

import type { ServerRow } from "@/types/server-scan-servers";

/** A healthy Dell, available, in no cluster; `overrides` replace its fields. */
export function serverRow(overrides: Partial<ServerRow> = {}): ServerRow {
  return {
    id: "srv_1",
    name: "srv-1",
    vendor: "dell",
    model: "R760",
    site_id: "tlv",
    source_provider: "OPENMANAGE",
    installation_type: "UPI",
    health: "HEALTHY",
    maintenance: { enabled: false, reason: null, created_by: null },
    reservation: { held: false, holder: null, mce_cluster: null, infra_env: null, expires_at: null },
    openshift_state: "AVAILABLE",
    cluster_name: null,
    mce_name: null,
    openshift_reported_name: null,
    contested_with: null,
    profile_template_name: null,
    last_seen_at: null,
    stale: false,
    reachable: true,
    serial: "SN1",
    bmc_host: "bmc-1.example",
    macs: ["aa:bb:cc:dd:ee:01"],
    ...overrides,
  };
}
