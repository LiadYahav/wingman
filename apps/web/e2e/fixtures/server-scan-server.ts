/**
 * A server's page's mocks (docs/notes/2026-11-13-server-scan-area-api.md §9),
 * typed so a shape change fails `tsc`: records in server-scan's own shape (a
 * healthy Dell node of the Servers fixture's fleet, a troubled Cisco UPI
 * server, a KubeVirt VM), its host, and two pages of History.
 */

import type { Page, Route } from "@playwright/test";
import { fulfillProblem, json } from "./api-handlers";
import { mockServers, setUpServers } from "./server-scan-servers";
import type { AuditEvent, AuditEventPage, ServerRecord, VmHostAnswer } from "../../types/server-scan-record";
import type { ServerRowsAnswer } from "../../types/server-scan-servers";

export const NODE = "ocp-dell-r660-site1-node-01";
export const NODE_ID = `srv_${NODE}`;
const CISCO = "ucs-cisco-site2-upi-07";
export const CISCO_ID = `srv_${CISCO}`;
export const VM_ID = "srv_vm-ocp-virt-01";
export const HOST_ID = "srv_ocp-dell-r760-site1-virt-03";

const GiB = 1024 ** 3;

/** The Servers fixture's first node, whole: a healthy Dell R660 of ocp4-prod-lark-site1. */
export function nodeRecord(overrides: Partial<ServerRecord> = {}): ServerRecord {
  return {
    id: NODE_ID,
    name: NODE,
    model: "PowerEdge R660",
    profile_template: { name: "R660-Standard", external_id: "tmpl-r660" },
    identity: { vendor: "dell", serial: "DL0101", system_uuid: "4c4c4544-0101", nic_macs: ["02:00:00:00:01:01", "02:00:00:00:01:02"] },
    hardware: {
      cpu: { sockets: 2, cores: 64, threads: 128, model: "Intel(R) Xeon(R) Platinum 8462Y+" },
      memory: {
        total_bytes: 1024 * GiB,
        modules: Array.from({ length: 16 }, (_, i) => ({ slot: `A${i + 1}`, size_bytes: 64 * GiB, speed_mhz: 4800, health: "HEALTHY", health_detail: "OK" })),
      },
      storage: {
        total_bytes: 4.8e12,
        drives: [
          { id: "Disk.Bay.1", model: "MZ7L33T8", serial: "S6XX01", media_type: "SSD", capacity_bytes: 3.84e12, health: "HEALTHY", health_detail: "OK" },
          { id: "Disk.Bay.0", model: "MZ7L3960", serial: "S6XX00", media_type: "SSD", capacity_bytes: 960e9, health: "WARNING", health_detail: "Predictive failure" },
        ],
        controllers: [
          { id: "RAID.SL.3-1", name: "PERC H755", kind: "RAID", volumes: [{ id: "Disk.Virtual.0", raid_type: "RAID1", volume_type: "Mirrored", capacity_bytes: 480e9, health: "HEALTHY" }] },
        ],
        raid: { state: "PRESENT", method: "redfish_storage", bmc: "iDRAC9", reason: null },
      },
      gpus: [],
      power: {
        psus: [
          { id: "PSU.Slot.1", model: "PWR SPLY,1400W", serial: "PS01", health: "HEALTHY", health_detail: null, capacity_watts: 1400, power_watts: 312 },
          { id: "PSU.Slot.2", model: null, serial: null, health: null, health_detail: null, capacity_watts: null, power_watts: null },
        ],
      },
    },
    network: {
      bmc: { address_raw: "https://192.0.2.101", scheme: "https", host: "192.0.2.101", port: null, mac: "02:00:00:00:01:ff" },
      interfaces: [
        { name: "NIC.Integrated.1-1-1", mac: "02:00:00:00:01:01", speed_mbps: 25000, link_state: "UP", location: "1/1/1" },
        { name: "NIC.Slot.8-1-1", mac: "02:00:00:00:01:02", speed_mbps: null, link_state: "DOWN", location: "8/1/1" },
      ],
    },
    connectivity: { attachments: [], facts: { fabric_paths_total: 0, fabric_paths_up: 0, fabric_paths_down: 0, fabrics_present: [] } },
    classification: { installation_type: "HOSTED_CLUSTER", matched_rule_id: "r1", matched_rule_name: "Hosted cluster nodes", matched_field: "name", matched_pattern: "^ocp-" },
    health: {
      overall: "HEALTHY", memory: "HEALTHY", storage: "WARNING", raid: "HEALTHY", network: "HEALTHY",
      connectivity: "UNKNOWN", power: "HEALTHY", gpu: "UNKNOWN", bmc: "HEALTHY", name: "HEALTHY", reasons: [],
    },
    maintenance: { enabled: false, reason: null, created_by: null, created_at: null, updated_at: null, expected_end: null },
    reservation: { held: false, holder: null, mce_cluster: null, infra_env: null, expires_at: null, namespace: null, workflow_id: null, created_at: null },
    site_id: "site1",
    manager_id: "openmanage-site1",
    source_provider: "OPENMANAGE",
    openshift: {
      lifecycle_state: "INSTALLED", cluster_name: "ocp4-prod-lark-site1", mce_name: "ocp4-prod-mce-site1-a",
      last_reported_at: "2026-11-13T07:55:00Z", reported_by_agent_id: "agent-0101", reported_name: null, contested_with: null, contested_name: null,
    },
    vm_host: null,
    unread_fields: [],
    nic_os_names: { "NIC.Integrated.1-1-1": "eno12399np0" },
    tags: [],
    last_seen_at: new Date(Date.now() - 3 * 3600_000).toISOString(),
    stale: false,
    reachable: true,
    unreachable_since: null,
    unreachable_reason: null,
    updated_at: "2026-11-13T08:00:00Z",
    created_at: "2026-09-01T06:00:00Z",
    maintenance_available: true,
    maintenance_detail: null,
    history_available: true,
    history_detail: null,
    ...overrides,
  };
}

const uplink = (fabric: string | null, name: string, port: string, overrides: Partial<ServerRecord["connectivity"]["attachments"][number]> = {}) => ({
  type: "FABRIC_INTERCONNECT", provider: "INTERSIGHT", fabric, fabric_name: name, fabric_id: name.toLowerCase(), fabric_model: "UCS-FI-6454",
  fabric_serial: `FCH${port}`, server_interface: "vic1", server_port: port, fabric_port: `Ethernet1/${port}`, admin_state: "ENABLED",
  oper_state: "UP" as const, speed_mbps: 25000, last_seen: "2026-11-13T07:00:00Z", interface_kind: "PHYSICAL", ...overrides,
});

/** A Cisco UPI server in trouble: critical with reasons, held by an install, renamed, claimed twice, its BMC refusing, stale, in maintenance. */
export function ciscoRecord(overrides: Partial<ServerRecord> = {}): ServerRecord {
  const base = nodeRecord();
  return {
    ...base,
    id: CISCO_ID,
    name: CISCO,
    model: null,
    profile_template: { name: "upi-worker-spt", external_id: null },
    identity: { ...base.identity, vendor: "cisco", serial: "FCH0707" },
    hardware: {
      ...base.hardware,
      memory: { total_bytes: 512 * GiB, modules: [] },
      gpus: [
        {
          vendor: "NVIDIA", model: "NVIDIA A100 80GB", serial: "GPU01", memory_bytes: 80 * GiB, health: "UP", health_detail: null, pci_address: "0000:17:00.0",
          firmware_version: "92.00.45", memory_type: "HBM2e", ecc_mode_enabled: true, correctable_error_count: 0, uncorrectable_error_count: 0,
          temperature_celsius: 41.4, power_watts: 88.2,
        },
      ],
    },
    connectivity: {
      attachments: [
        uplink("A", "FI-A-SITE2", "17"),
        uplink("A", "FI-A-SITE2", "17", { interface_kind: "VNIC", server_interface: "eth0" }),
        uplink("B", "FI-B-SITE2", "18", { oper_state: "DOWN" }),
        uplink(null, "FI-X", "19"),
      ],
      facts: { fabric_paths_total: 3, fabric_paths_up: 2, fabric_paths_down: 1, fabrics_present: ["A", "B"] },
    },
    classification: { installation_type: "UPI", matched_rule_id: null, matched_rule_name: null, matched_field: null, matched_pattern: null },
    health: {
      ...base.health,
      overall: "CRITICAL",
      storage: "CRITICAL",
      connectivity: "MAJOR",
      reasons: [
        { policy_key: "storage.name_capacity_mismatch", policy_name: "Storage doesn't match the server's own name", category: "storage", severity: "CRITICAL", message: "4.80 TB of storage, but the name promises 10.00 TB" },
        { policy_key: "connectivity.fabric_path_down", policy_name: "A fabric path is down", category: "connectivity", severity: "MAJOR", message: null },
      ],
    },
    maintenance: { enabled: true, reason: "PSU swap", created_by: "api-token-admin", created_at: "2026-11-12T09:00:00Z", updated_at: null, expected_end: "2026-11-14T14:00:00Z" },
    reservation: {
      held: true, holder: "add-server-to-mce", mce_cluster: "ocp4-prod-mce-site1-b", infra_env: "ucs-c240", expires_at: null,
      namespace: "ucs-c240", workflow_id: "add-server-to-mce-x", created_at: "2026-11-13T07:00:00Z",
    },
    site_id: "site2",
    manager_id: "intersight-site2",
    source_provider: "INTERSIGHT",
    openshift: {
      ...base.openshift, cluster_name: "ocp4-upi-orca", mce_name: null, reported_name: "ucs-cisco-site2-old-07",
      contested_with: "ocp4-upi-other", contested_name: "ocp-old-node-07",
    },
    unread_fields: ["hardware.memory.total_bytes", "hardware.storage.drives"],
    nic_os_names: {},
    stale: true,
    reachable: false,
    unreachable_reason: "auth_rejected",
    unreachable_since: "2026-11-12T06:00:00Z",
    ...overrides,
  };
}

/** A KubeVirt VM: no BMC, no power, no template; it runs on a Dell of the fleet. */
export function vmRecord(): ServerRecord {
  const base = nodeRecord();
  return {
    ...base,
    id: VM_ID,
    name: "vm-ocp-virt-01",
    model: null,
    profile_template: { name: null, external_id: null },
    identity: { ...base.identity, vendor: "kubevirt", serial: null },
    hardware: { ...base.hardware, gpus: [] },
    network: { bmc: { address_raw: null, scheme: null, host: null, port: null, mac: null }, interfaces: [] },
    source_provider: "KUBEVIRT",
    vm_host: { cluster_name: "ocp4-prod-virt-site1", node_name: "worker-3" },
  };
}

const VM_HOST: VmHostAnswer = {
  cluster_name: "ocp4-prod-virt-site1",
  node_name: "worker-3",
  match: "MEMBERSHIP",
  host: {
    id: HOST_ID, name: "ocp-dell-r760-site1-virt-03", vendor: "dell", model: "PowerEdge R760", site_id: "site1",
    cpu: { sockets: 2, cores: 96, threads: 192, model: "AMD EPYC 9654" }, memory_total_bytes: 1536 * GiB, health: "WARNING",
    maintenance: true, cluster_name: "ocp4-prod-virt-site1",
  },
};

const event = (id: string, event_type: string, created_at: string, data: Record<string, unknown>, actor: AuditEvent["actor"] = { type: "SYSTEM", id: "ingest", display: null }): AuditEvent => ({
  id, event_type, server_id: NODE_ID, server_name: NODE, actor, request_id: null, created_at, data,
});

/** Two pages of the node's History, newest first: a Wingman maintenance, a health change, then its discovery. */
const HISTORY: AuditEventPage[] = [
  {
    items: [
      event("e3", "MAINTENANCE_ENABLED", "2026-11-12T09:14:00Z", { reason: "Replacing PSU 2 — INC-4417" }, { type: "TOKEN", id: "api-token-admin", display: null }),
      event("e2", "HEALTH_CHANGED", "2026-11-11T08:00:00Z", {
        from: "HEALTHY",
        to: "WARNING",
        from_reasons: [],
        to_reasons: [{ policy_key: "storage.predictive_failure", policy_name: "A drive predicts its failure", category: "storage", severity: "WARNING", message: "Disk.Bay.0 predicts failure" }],
      }),
    ],
    page: { next_cursor: "c2", has_more: true, page_size: 2, total: 3 },
  },
  {
    items: [event("e1", "SERVER_CREATED", "2026-09-01T06:00:00Z", { vendor: "dell", name: NODE })],
    page: { next_cursor: null, has_more: false, page_size: 2, total: null },
  },
];

type Handler = (route: Route) => Promise<void> | void;

/** What the page asked: every History read's cursor ("" for the first page), and every maintenance change. */
export interface ServerCalls {
  history: string[];
  changes: { method: string; body: unknown }[];
  recordReads: () => number;
}

/**
 * Sign in as an admin and mock the Sites and Servers reads, then the server
 * routes: each record by its id (a `Handler` answers instead), its VM host,
 * its History by cursor, and maintenance changes that edit the record, so
 * the next read shows them. Register a test's own routes after this.
 */
export async function setUpServer(
  page: Page,
  {
    records = [nodeRecord()],
    record,
    history = HISTORY,
    vmHost = VM_HOST,
    servers = mockServers(),
  }: { records?: ServerRecord[]; record?: Handler; history?: AuditEventPage[] | Handler; vmHost?: VmHostAnswer | Handler; servers?: ServerRowsAnswer } = {}
): Promise<ServerCalls> {
  let reads = 0;
  const calls: ServerCalls = { history: [], changes: [], recordReads: () => reads };
  const byId = new Map(records.map((r) => [r.id, r]));
  await setUpServers(page, { servers });
  await page.route(/\/api\/day1\/server-scan\/servers\/[^/?]+$/, (route) => {
    reads += 1;
    if (record) return record(route);
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split("/").at(-1) ?? "");
    const found = byId.get(id);
    return found ? json(route, found) : fulfillProblem(route, 404, "NOT_FOUND", `server-scan has no server '${id}'`);
  });
  await page.route(/\/api\/day1\/server-scan\/servers\/[^/]+\/vm-host$/, (route) => (typeof vmHost === "function" ? vmHost(route) : json(route, vmHost)));
  await page.route(/\/api\/day1\/server-scan\/servers\/[^/]+\/events(\?.*)?$/, (route) => {
    const cursor = new URL(route.request().url()).searchParams.get("cursor") ?? "";
    calls.history.push(cursor);
    if (typeof history === "function") return history(route);
    return json(route, cursor === "c2" ? history[1] : history[0]);
  });
  await page.route(/\/api\/day1\/server-scan\/servers\/[^/]+\/maintenance$/, (route) => {
    const request = route.request();
    const id = decodeURIComponent(new URL(request.url()).pathname.split("/").at(-2) ?? "");
    const body = request.postData() ? (JSON.parse(request.postData() ?? "null") as { reason: string | null; expected_end: string | null }) : null;
    calls.changes.push({ method: request.method(), body });
    const found = byId.get(id);
    if (!found) return fulfillProblem(route, 404, "NOT_FOUND", `server-scan has no server '${id}'`);
    found.maintenance = body
      ? { enabled: true, reason: body.reason, created_by: "api-token-admin", created_at: "2026-11-14T08:00:00Z", updated_at: null, expected_end: body.expected_end }
      : { enabled: false, reason: null, created_by: null, created_at: null, updated_at: null, expected_end: null };
    const { enabled, reason, created_by } = found.maintenance;
    return json(route, { id, name: found.name, maintenance: { enabled, reason, created_by } });
  });
  return calls;
}
