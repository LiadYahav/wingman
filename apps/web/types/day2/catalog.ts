import type { Finding } from "./destinations";
import type { SyncSettings } from "./sync-options";

// ── Catalog (ADR-0024) ───────────────────────────────────────────────────────

/** The add-on's deploy config (`operators/<chart>/<chart>.yaml`), legacy spelling. */
export interface ArgoMetadata {
  projectNamespace: string;
  /** "" when the add-on only has the miscased `repoUrl` (see `warnings`). */
  repourl: string;
  /** Defaults to `HEAD`: the chart repo's default branch. */
  targetRevision: string;
  syncPolicy: Record<string, unknown>;
  path: string;
}

/** An `operators/<chart>/ocp-versions/<version>/` pin. */
export interface OcpVersionPin {
  version: string;
  target_revision: string | null;
}

/** `GET /api/day2/addons`: a team catalog entry (`operators/<chart>/`). */
export interface CatalogEntry {
  team: string;
  name: string;
  /** The chart repo's branches: default branch first, then newest release first. */
  available_versions: string[];
  /** The add-on's `targetRevision`, else `HEAD`. */
  current_version: string;
  /** The Sig values, `operators/<chart>/values.yaml`, verbatim. */
  default_values: Record<string, unknown>;
  argocd_metadata: ArgoMetadata;
  /** Always empty: day2 has no dependency concept. Kept for the legacy shape. */
  dependencies: string[];
  ocp_version_pins: OcpVersionPin[];
  /** The fleet-default scopes (`hub`, `mces`, `hosted-clusters`, `upi`) that deploy it everywhere. */
  fleet_defaults: string[];
  /** The chart repo on this GitLab, `null` when the repourl is missing or elsewhere. */
  chart_project: string | null;
  warnings: Finding[];
  /** Wingman may write to the team's repo (ADR-0043). */
  writable: boolean;
  read_only_reason: string | null;
  /** What `operators/<chart>/<chart>.yaml` sets (a pin, a fleet default or a folder may override it). */
  sync: SyncSettings;
  ignore_differences: unknown[] | null;
  deploy_config_exists: boolean;
  /** The commit the entry was read at: send it back on edit. */
  last_commit_id: string | null;
}
