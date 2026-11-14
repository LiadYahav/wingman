/**
 * The Server Scan area's server page: one server's record, the host a VM
 * runs on, and the server's History, which day1 passes through typed and in
 * server-scan's own shapes (docs/notes/2026-11-13-server-scan-area-api.md §9,
 * ADR-0048's 3.25.0 amendment). Admins only.
 *
 * Ported from team-redbull/server-scan at 92146d3 (decision 18 of the
 * single-pane plan): `frontend/src/types/server.ts` (`ServerDetail`,
 * `VmHostResponse`) and `frontend/src/types/events.ts`. As there, `X | null`
 * means "always sent, may be null". day1 adds the maintenance's dates,
 * `reservation.held` and whether the toggle and History work here.
 */

import type { HealthSeverity, InstallationType, OpenShiftState, Vendor } from "./server-scan";
import type { MaintenanceState, ReservationState } from "./server-scan-servers";

export type LinkState = "UP" | "DOWN" | "UNKNOWN" | "DISABLED";

export type UnreachableReason =
  | "network_unreachable"
  | "auth_rejected"
  | "tls_error"
  | "timeout"
  | "protocol_error"
  | "not_an_idrac";

/** Not narrowed to a severity: Cisco and the Redfish PSU path report UP, DOWN, DISABLED or UNKNOWN. */
export type ComponentHealth = string | null;

/** Null for a standalone server (a bare BMC has no template) or when it was not read this run. */
export interface ProfileTemplate {
  name: string | null;
  external_id: string | null;
}

export interface ServerIdentity {
  vendor: Vendor;
  serial: string | null;
  system_uuid: string | null;
  nic_macs: string[];
}

export interface CpuInfo {
  sockets: number;
  cores: number;
  threads: number;
  model: string | null;
}

export interface MemoryModule {
  slot: string | null;
  size_bytes: number | null;
  speed_mhz: number | null;
  health: ComponentHealth;
  /** The vendor's raw word `health` was reduced from; diagnosis only. */
  health_detail: string | null;
}

export interface MemoryInfo {
  total_bytes: number;
  modules: MemoryModule[];
}

export interface StorageDrive {
  id: string;
  model: string | null;
  serial: string | null;
  media_type: string;
  capacity_bytes: number | null;
  health: ComponentHealth;
  health_detail: string | null;
}

export interface StorageVolume {
  id: string;
  raid_type: string | null;
  volume_type: string | null;
  capacity_bytes: number | null;
  health: ComponentHealth;
}

export interface StorageController {
  id: string;
  name: string | null;
  /** `RAID`, `BOSS`, `AHCI`, `NVME` or `OTHER`. */
  kind: string;
  volumes: StorageVolume[];
}

/** Whether the OS sits on RAID 1: `PRESENT`, `ABSENT` or `UNKNOWN`, and which BMC and method said so. */
export interface RaidDetection {
  state: string;
  method: string | null;
  bmc: string | null;
  reason: string | null;
}

export interface StorageInfo {
  total_bytes: number;
  drives: StorageDrive[];
  /** Empty on a document written before RAID was collected. */
  controllers: StorageController[];
  /** Null on a document written before RAID detection. */
  raid: RaidDetection | null;
}

export interface GpuInfo {
  vendor: string | null;
  model: string | null;
  serial: string | null;
  memory_bytes: number | null;
  health: ComponentHealth;
  health_detail: string | null;
  pci_address: string | null;
  firmware_version: string | null;
  memory_type: string | null;
  ecc_mode_enabled: boolean | null;
  correctable_error_count: number | null;
  uncorrectable_error_count: number | null;
  temperature_celsius: number | null;
  power_watts: number | null;
}

export interface PsuInfo {
  id: string;
  model: string | null;
  serial: string | null;
  health: ComponentHealth;
  health_detail: string | null;
  capacity_watts: number | null;
  power_watts: number | null;
}

export interface HardwareInfo {
  cpu: CpuInfo;
  memory: MemoryInfo;
  storage: StorageInfo;
  gpus: GpuInfo[];
  power: { psus: PsuInfo[] };
}

export interface BmcInfo {
  address_raw: string | null;
  scheme: string | null;
  host: string | null;
  port: number | null;
  mac: string | null;
}

export interface NetworkInterface {
  name: string;
  mac: string | null;
  speed_mbps: number | null;
  link_state: LinkState;
  /** `controller/port/partition` on Dell (`1/1/1`), the BMC's raw id elsewhere. */
  location: string | null;
}

export interface NetworkInfo {
  bmc: BmcInfo;
  interfaces: NetworkInterface[];
}

/** `fabric` is a free label (not always A and B); `null` is shown under "Other". */
export interface ConnectivityAttachment {
  type: string;
  provider: string | null;
  fabric: string | null;
  fabric_name: string | null;
  fabric_id: string | null;
  fabric_model: string | null;
  fabric_serial: string | null;
  server_interface: string | null;
  server_port: string | null;
  fabric_port: string | null;
  admin_state: string;
  oper_state: LinkState;
  speed_mbps: number | null;
  last_seen: string | null;
  /** `PHYSICAL` for a cabled uplink, `VNIC` for a carve-out on it (both report the same fabric). */
  interface_kind: string;
}

export interface ConnectivityDetail {
  attachments: ConnectivityAttachment[];
  facts: {
    fabric_paths_total: number;
    fabric_paths_up: number;
    fabric_paths_down: number;
    fabrics_present: string[];
  };
}

export interface Classification {
  installation_type: InstallationType;
  matched_rule_id: string | null;
  matched_rule_name: string | null;
  matched_field: string | null;
  matched_pattern: string | null;
}

/** One policy that fired in the last evaluation, worst first. */
export interface HealthReason {
  policy_key: string;
  policy_name: string;
  category: string;
  severity: HealthSeverity;
  message: string | null;
}

export interface HealthSummary {
  overall: HealthSeverity;
  memory: HealthSeverity;
  storage: HealthSeverity;
  network: HealthSeverity;
  raid: HealthSeverity;
  connectivity: HealthSeverity;
  power: HealthSeverity;
  gpu: HealthSeverity;
  bmc: HealthSeverity;
  name: HealthSeverity;
  reasons: HealthReason[];
}

/** A server's maintenance, with server-scan's dates: when it began, last changed, and should end. */
export interface RecordMaintenance extends MaintenanceState {
  created_at: string | null;
  updated_at: string | null;
  expected_end: string | null;
}

/** The install lock; `held` is judged by day1 with server-scan's rule for its rows. */
export interface RecordReservation extends ReservationState {
  namespace: string | null;
  workflow_id: string | null;
  created_at: string | null;
}

/** OpenShift's own report, never reconciled with the classification: their disagreeing is the signal. */
export interface OpenShiftLifecycle {
  lifecycle_state: OpenShiftState;
  cluster_name: string | null;
  mce_name: string | null;
  last_reported_at: string | null;
  reported_by_agent_id: string | null;
  /** Set only when it differs from the server's name (a rename after install). */
  reported_name: string | null;
  /** The other cluster or MCE also claiming it, and the hostname it reports. */
  contested_with: string | null;
  contested_name: string | null;
}

/** Where a KubeVirt VM runs; `null` for every physical server. */
export interface VmHost {
  cluster_name: string | null;
  /** `null` while the VM is stopped. */
  node_name: string | null;
}

/** `GET /api/day1/server-scan/servers/{id}`: the record (§9.4). */
export interface ServerRecord {
  id: string;
  name: string;
  model: string | null;
  profile_template: ProfileTemplate;
  identity: ServerIdentity;
  hardware: HardwareInfo;
  network: NetworkInfo;
  connectivity: ConnectivityDetail;
  classification: Classification;
  health: HealthSummary;
  maintenance: RecordMaintenance;
  reservation: RecordReservation;
  site_id: string | null;
  manager_id: string | null;
  source_provider: string | null;
  openshift: OpenShiftLifecycle;
  vm_host: VmHost | null;
  /** Dotted paths the last collection could not read: the value there is carried forward or a zero. */
  unread_fields: string[];
  /** NIC FQDD → OS interface name, from server-scan's settings (never collected). */
  nic_os_names: Record<string, string>;
  tags: string[];
  last_seen_at: string | null;
  stale: boolean;
  reachable: boolean;
  unreachable_since: string | null;
  unreachable_reason: UnreachableReason | null;
  updated_at: string;
  created_at: string;
  /** Whether the maintenance toggle works here (§8.4), and why not in one line. */
  maintenance_available: boolean;
  maintenance_detail: string | null;
  /** Whether History works here (the auditor token, §9.5), and why not in one line. */
  history_available: boolean;
  history_detail: string | null;
}

// ── GET /api/day1/server-scan/servers/{id}/vm-host ────────────────────────────

/** How the VM's node was resolved, most certain first. */
export type HostMatch = "MEMBERSHIP" | "NAME" | "AMBIGUOUS" | "NOT_IN_INVENTORY" | "NOT_RUNNING";

export interface VmHostServer {
  id: string;
  name: string;
  vendor: Vendor;
  model: string | null;
  site_id: string | null;
  cpu: CpuInfo;
  memory_total_bytes: number | null;
  health: HealthSeverity;
  maintenance: boolean;
  cluster_name: string | null;
}

/** `host` is set only for a `MEMBERSHIP` or `NAME` match. */
export interface VmHostAnswer {
  cluster_name: string | null;
  node_name: string | null;
  match: HostMatch;
  host: VmHostServer | null;
}

// ── GET /api/day1/server-scan/servers/{id}/events ─────────────────────────────

export type ActorType = "SYSTEM" | "USER" | "TOKEN";

export interface Actor {
  type: ActorType;
  id: string;
  display: string | null;
}

export interface AuditEvent {
  id: string;
  /** A free string: server-scan writes more types than the page names. */
  event_type: string;
  server_id: string | null;
  server_name: string | null;
  actor: Actor;
  request_id: string | null;
  created_at: string;
  data: Record<string, unknown>;
}

export interface AuditEventPage {
  items: AuditEvent[];
  page: {
    next_cursor: string | null;
    has_more: boolean;
    page_size: number;
    /** Matching events in all; on the first page only. */
    total?: number | null;
  };
}
