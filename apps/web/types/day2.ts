// The day2 service's response and request bodies, field for field with
// apps/day2-service/src/wingman_day2/api/v1/schemas.py (the truth when this
// file and the service disagree). What changed for the web app, and why, is in
// docs/notes/2026-11-07-day2-api-changes.md and ADRs 0020-0024.

// ── Destinations (ADR-0020) ──────────────────────────────────────────────────

/** The four destination kinds; each has its own folder, Argo instance and value stack. */
export type DestinationKind = "hub" | "mce" | "hosted" | "upi";

/**
 * A lint finding (ADR-0023). `cluster` is a destination id, `chart` a chart
 * name; either is "" when the finding is not about one.
 */
export interface Finding {
  rule: string;
  severity: "error" | "warning" | "info" | (string & {});
  message: string;
  team: string;
  path: string;
  cluster: string;
  chart: string;
}

/** One destination: `GET /api/day2/clusters`, `GET /api/day2/clusters/{id}`. */
export interface Destination {
  /** `hub`, `mce:<site>:<env>:<mce>`, `hosted:<site>:<env>:<mce>:<cluster>` or `upi:<site>:<env>:<cluster>`. */
  id: string;
  kind: DestinationKind;
  name: string;
  site: string;
  /** "" when no team repo or name gives one; such a destination cannot be written to. */
  env: string;
  mce: string;
  ocp_version: string | null;
  /** The ArgoCD instance its leaf apps live on. */
  argo: string;
  teams: string[];
  in_day1: boolean;
  warnings: Finding[];
}

export interface GitLabInfo {
  gitlab_url: string;
  sigs_group_path: string;
  sigs_group_url: string;
}

// ── Catalog (ADR-0024) ───────────────────────────────────────────────────────

/** The team default deploy config (`operators/<chart>/<chart>.yaml`), legacy spelling. */
export interface ArgoMetadata {
  projectNamespace: string;
  /** "" when the team default only has the miscased `repoUrl` (see `warnings`). */
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
  /** The team default `targetRevision`, else `HEAD`. */
  current_version: string;
  /** The team's `values.yaml`, verbatim. */
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
}

// ── Charts on a destination ──────────────────────────────────────────────────

/** The leaf ArgoCD Application the platform generates for a chart on a destination. */
export interface LeafApp {
  app_name: string;
  argo: string;
  namespace: string;
  repo_url: string;
  target_revision: string;
  path: string;
  release_name: string;
  destination: string;
  destination_namespace: string | null;
  sync_policy: unknown;
  auto_sync: boolean;
}

export type ChartSource = "cluster" | "fleet-default";

/** One chart the platform generates an app for on a destination. */
export interface InstalledChart {
  team: string;
  name: string;
  /** The effective `targetRevision`. */
  version: string;
  /** The contents of `override_path`: what an update rewrites. */
  override_values: Record<string, unknown>;
  parse_errors: Finding[];
  gitlab_url: string;
  source: ChartSource | (string & {});
  /** The chart's folder (its own, or the fleet default's). */
  path: string;
  /** The file an edit writes: the folder's `values.yaml`, or `values-<cluster>.yaml` for a fleet default. */
  override_path: string;
  /** Send it back on update and remove; a stale one is 409. */
  last_commit_id: string | null;
  /** An emergency pin: the cluster folder sets its own `targetRevision`. */
  pinned: boolean;
  deploy: LeafApp;
  warnings: Finding[];
}

/** A fleet default kept off the destination by `exclusions.yaml`. */
export interface ExcludedDefault {
  team: string;
  name: string;
  scope: string;
}

/** `GET /api/day2/clusters/{id}/addons`. */
export interface DestinationCharts {
  cluster: string;
  mce: string;
  id: string;
  kind: DestinationKind;
  site: string;
  env: string;
  ocp_version: string | null;
  installed: InstalledChart[];
  excluded: ExcludedDefault[];
  warnings: Finding[];
  argocd_note: string;
}

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

// ── Writes (ADR-0022) ────────────────────────────────────────────────────────

export interface InstallBody {
  override_values: Record<string, unknown>;
  /** Honoured only if equal to the inherited revision, or with `emergency_pin`. */
  version?: string;
  emergency_pin?: boolean;
  /** Needed only when no layer has a lowercase repourl. */
  repourl?: string;
  project_namespace?: string;
  message?: string;
}

export interface UpdateBody {
  override_values: Record<string, unknown>;
  version?: string;
  emergency_pin?: boolean;
  last_commit_id?: string | null;
  message?: string;
}

export interface BulkItem {
  team: string;
  addon: string;
  version?: string;
  emergency_pin?: boolean;
  override_values: Record<string, unknown>;
}

export interface BulkBody {
  addons: BulkItem[];
  custom_message?: string;
}

export interface MergePreviewBody {
  team: string;
  addon: string;
  cluster: string;
  mce?: string;
  version?: string;
  override_values?: Record<string, unknown>;
}

/** A day2 merge request (`MRDetailOut`). */
export interface Day2MergeRequest {
  iid: number;
  title: string;
  description: string;
  author: { username: string; name: string; avatar_url: string | null };
  state: string;
  created_at: string;
  updated_at: string;
  web_url: string;
  source_branch: string;
  target_branch: string;
  labels: string[];
  repo: "day2";
  has_conflicts: boolean | null;
  team: string;
  project_id: number;
  /** The MR head: what an approver reviews. */
  sha: string;
  gitlab_author: string;
}

export interface FileChange {
  action: "create" | "update" | "delete" | "move" | (string & {});
  path: string;
}

/** An opened MR plus what it writes and what to expect after the merge. */
export interface ChangeResult extends Day2MergeRequest {
  cluster: string;
  files: FileChange[];
  app_names: string[];
  warnings: Finding[];
  /** Read these: what else the change registers, sync, and that a removal orphans. */
  notes: string[];
}

/** `POST /api/day2/clusters/{id}/addons/bulk`: one MR per team. */
export interface BulkResult {
  merge_requests: ChangeResult[];
  failed: { team: string; error: string; detail: string }[];
}

/** `GET /api/day2/clusters/{id}/upgrade-check?to=`. */
export interface UpgradeCheck {
  cluster: string;
  from_version: string | null;
  to_version: string;
  warnings: Finding[];
}
