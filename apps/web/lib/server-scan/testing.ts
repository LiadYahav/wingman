/**
 * Servers for the unit tests (made up), in server-scan's shapes: a row
 * (docs/notes/2026-11-13-server-scan-area-api.md §8.3), a record and an
 * event (§9.4), the record as server-scan's own `OverviewTab.test.tsx` makes it.
 */

import type { AuditEvent, GpuInfo, ServerRecord } from "@/types/server-scan-record";
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

/** A GPU whose every reading is unread but its model; `overrides` replace its fields. */
export function gpu(overrides: Partial<GpuInfo> = {}): GpuInfo {
  return {
    vendor: "NVIDIA",
    model: "NVIDIA A100 80GB",
    serial: null,
    memory_bytes: null,
    health: null,
    health_detail: null,
    pci_address: null,
    firmware_version: null,
    memory_type: null,
    ecc_mode_enabled: null,
    correctable_error_count: null,
    uncorrectable_error_count: null,
    temperature_celsius: null,
    power_watts: null,
    ...overrides,
  };
}

/** A UCS Central server's record, healthy, in no cluster (server-scan's own test server); `overrides` replace its fields. */
export function serverRecord(overrides: Partial<ServerRecord> = {}): ServerRecord {
  return {
    id: "srv_1",
    name: "ocp-dell-worker-000",
    model: "PowerEdge R6515",
    profile_template: { name: null, external_id: null },
    identity: { vendor: "dell", serial: "SN123", system_uuid: null, nic_macs: [] },
    hardware: {
      cpu: { sockets: 2, cores: 32, threads: 64, model: "Xeon Gold 6338" },
      memory: { total_bytes: 0, modules: [] },
      storage: { total_bytes: 0, drives: [], controllers: [], raid: null },
      gpus: [],
      power: { psus: [] },
    },
    network: { bmc: { address_raw: null, scheme: null, host: null, port: null, mac: null }, interfaces: [] },
    connectivity: { attachments: [], facts: { fabric_paths_total: 0, fabric_paths_up: 0, fabric_paths_down: 0, fabrics_present: [] } },
    classification: { installation_type: "HOSTED_CLUSTER", matched_rule_id: null, matched_rule_name: null, matched_field: null, matched_pattern: null },
    health: {
      overall: "HEALTHY", memory: "HEALTHY", storage: "HEALTHY", raid: "UNKNOWN", network: "HEALTHY",
      connectivity: "HEALTHY", power: "HEALTHY", gpu: "UNKNOWN", bmc: "UNKNOWN", name: "UNKNOWN", reasons: [],
    },
    maintenance: { enabled: false, reason: null, created_by: null, created_at: null, updated_at: null, expected_end: null },
    reservation: {
      held: false, holder: null, mce_cluster: null, infra_env: null, expires_at: null, namespace: null, workflow_id: null, created_at: null,
    },
    site_id: "tlv",
    manager_id: "mgr_1",
    source_provider: "UCS_CENTRAL",
    openshift: {
      lifecycle_state: "AVAILABLE", cluster_name: null, mce_name: null, last_reported_at: null,
      reported_by_agent_id: null, reported_name: null, contested_with: null, contested_name: null,
    },
    vm_host: null,
    unread_fields: [],
    nic_os_names: {},
    tags: [],
    last_seen_at: "2026-08-13T10:00:00Z",
    stale: false,
    reachable: true,
    unreachable_since: null,
    unreachable_reason: null,
    updated_at: "2026-08-13T10:00:00Z",
    created_at: "2026-08-13T10:00:00Z",
    maintenance_available: true,
    maintenance_detail: null,
    history_available: true,
    history_detail: null,
    ...overrides,
  };
}

/** One audit event on `srv_1`, by the system; `data` is what its writer recorded. */
export function auditEvent(event_type: string, data: Record<string, unknown> = {}): AuditEvent {
  return {
    id: "e",
    event_type,
    server_id: "srv_1",
    server_name: "ocp-worker-001",
    actor: { type: "SYSTEM", id: "sys", display: null },
    request_id: null,
    created_at: "2026-08-12T10:00:00Z",
    data,
  };
}
