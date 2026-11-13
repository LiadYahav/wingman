/**
 * Inventory Management: day1's typed view (docs/notes/2026-11-13-inventory-management-api.md,
 * ADR-0057). Everyone signed in reads; only admins add. `501 FEATURE_DISABLED`
 * without server-scan.
 */

// ── GET /api/day1/inventory ───────────────────────────────────────────────────

export interface Availability {
  available: boolean;
  /** Why not, when not. */
  detail: string | null;
}

export interface HardwareCount {
  vendor: string | null;
  model: string | null;
  available: number;
  usable: number;
}

export interface PoolCount {
  /** `null`: available servers whose name matches no InfraEnv on the MCE. */
  infra_env: string | null;
  /** Agents in the MCE's inventory, in no cluster (server-scan's INSTALLED_TO_INVENTORY). */
  available: number;
  usable: number;
  hardware: HardwareCount[];
  /** Servers in no MCE that a pool draw could pick (server-scan's view); `null` without an InfraEnv. */
  drawable: number | null;
}

export interface MceInventory {
  site: string;
  mce: string;
  /** `false`: server-scan names no server on it, so its counts are unknown, not 0. */
  known: boolean;
  servers: number;
  in_clusters: number;
  available: number;
  usable: number;
  pools: PoolCount[];
  infra_envs: string[];
  infra_envs_error: string | null;
}

export interface InventoryOverview {
  mces: MceInventory[];
  add_servers: Availability;
  runs: Availability;
}

// ── GET .../infra-envs/{infra_env}/candidates ─────────────────────────────────

/** server-scan's lock (its reservation) while held. */
export interface ServerLock {
  holder: string;
  mce: string | null;
  infra_env: string | null;
  expires_at: string | null;
}

export interface Candidate {
  id: string;
  name: string;
  vendor: string | null;
  model: string | null;
  health: string;
  lock: ServerLock | null;
  offered: boolean;
  /** Why a named install would fail on it: locked, in maintenance, contested. */
  why_not: string | null;
}

export interface Candidates {
  mce: string;
  infra_env: string;
  candidates: Candidate[];
}

// ── GET /api/day1/inventory/runs ──────────────────────────────────────────────

/** `named`: a person's. `pool`: herzi's or a person's; nothing tells which. */
export type RunOrigin = "named" | "pool";

export interface InventoryRun {
  workflow_id: string;
  status: string;
  started_at: string | null;
  closed_at: string | null;
  mce: string | null;
  infra_env: string | null;
  slot: number | null;
  server_name: string | null;
  origin: RunOrigin | null;
  /** The workflow's own word, passed through. */
  phase: string | null;
  error: string | null;
}

export interface InventoryRuns {
  runs: InventoryRun[];
}

// ── POST .../add-servers ──────────────────────────────────────────────────────

export type AddServersRequest = { count: number } | { server_names: string[] };

export interface StartedRun {
  workflow_id: string;
  /** `started`, `already_running` or `failed`: the orchestrator's word. */
  status: string;
  server_name: string | null;
  slot: number | null;
  error: string | null;
}

export interface AddServersResult {
  started: number;
  already_running: number;
  failed: number;
  runs: StartedRun[];
}
