import type { ChartSource, LeafApp } from "./charts";
import type { Finding } from "./destinations";

// ── Values preview (ADR-0021) ────────────────────────────────────────────────

/**
 * Who set a value, as the layer's role, lowest first. Each kind has its own
 * subset; an unknown string is shown as-is.
 */
export type LayerRole =
  | "chart"
  | "hub"
  | "team"
  | "team-ocp-version"
  | "site"
  | "site-env"
  | "fleet"
  | "fleet-env"
  | "fleet-target"
  | "mce"
  | "upi-wide"
  | "cluster-wide"
  | "cluster"
  | (string & {});

/** One layer of a value stack. */
export interface ValueLayer {
  role: LayerRole;
  path: string;
  exists: boolean;
  values: Record<string, unknown>;
  last_commit_id: string | null;
  problem: string | null;
}

/** Where chart defaults were read from, or why they were not. */
export interface ChartValuesSource {
  project: string | null;
  revision: string;
  path: string;
  problem: string | null;
}

/** The leaf plus its deploy-config stack; `provenance` leaves are file paths. */
export interface DeployPreview extends LeafApp {
  layers: ValueLayer[];
  provenance: Record<string, unknown>;
}

/**
 * Provenance has the merged values' shape; every leaf is the role of the
 * layer that set it.
 */
export type Provenance = { [key: string]: Provenance | LayerRole };

/** `GET /api/day2/clusters/{id}/addons/{team}/{chart}` and `POST /api/day2/merge-preview`. */
export interface ValuesPreview {
  merged: Record<string, unknown>;
  provenance: Provenance;
  chart_values: Record<string, unknown>;
  team_values: Record<string, unknown>;
  cluster_values: Record<string, unknown>;
  addon_name: string;
  team: string;
  /** The chart revision used (`HEAD` when unpinned). */
  version: string;
  /** The destination id. */
  cluster: string;
  installed: boolean;
  source: ChartSource | (string & {});
  ocp_version: string | null;
  chart: ChartValuesSource;
  layers: ValueLayer[];
  deploy: DeployPreview;
  warnings: Finding[];
}
