// The day2 service's response and request bodies, field for field with
// apps/day2-service/src/wingman_day2/api/v1/*schemas.py (the truth when this
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

// ── Teams and their write access (ADR-0043) ───────────────────────────────────

/** GitLab's role names, lowest first; `none` is no membership at all. */
export type AccessRole =
  | "none"
  | "minimal"
  | "guest"
  | "planner"
  | "reporter"
  | "developer"
  | "maintainer"
  | "owner"
  /** Wingman could not read the account's access to the project: the team is read-only (ADR-0053). */
  | "unknown"
  | (string & {});

/**
 * `GET /api/day2/teams`, `GET /api/day2/teams/{team}`: a team, its project,
 * and whether Wingman's GitLab account may write there (Developer or higher on
 * the project). A read-only team's writes are refused with `TEAM_READ_ONLY`.
 */
export interface Team {
  name: string;
  project_id: number;
  path_with_namespace: string;
  web_url: string;
  writable: boolean;
  /** GitLab's number: 0 none … 20 reporter, 30 developer, 40 maintainer, 50 owner. */
  access_level: number;
  access_role: AccessRole;
  /** One sentence to show as is; `null` when `writable`. */
  read_only_reason: string | null;
}

// ── Sync options (ADR-0043) ──────────────────────────────────────────────────

/** The leaf app's ArgoCD `syncPolicy`, as four settings. */
export interface SyncSettings {
  /** `syncPolicy.automated` is present: ArgoCD syncs by itself after the merge. */
  auto_sync: boolean;
  /** `automated.prune`; only with `auto_sync`. */
  prune: boolean;
  /** `automated.selfHeal`; only with `auto_sync`. */
  self_heal: boolean;
  /** `syncPolicy.syncOptions`, in order, each `Name=value`. */
  sync_options: string[];
}

/** A `defaults/<scope>/` folder: `hub`, `mces`, `hosted-clusters` or `upi`. */
export type FleetScope = "hub" | "mces" | "hosted-clusters" | "upi";

/** A fleet scope and the destinations a default there reaches today. */
export interface ScopeReach {
  scope: FleetScope;
  /** "every hosted cluster", "every MCE", "the hub", "every UPI cluster". */
  label: string;
  destinations: string[];
}

/** `GET /api/day2/teams/{team}/addon-template`: what the New add-on form starts from. */
export interface AddonTemplate {
  team: string;
  writable: boolean;
  read_only_reason: string | null;
  sync: SyncSettings;
  /** Where `sync` comes from, for a hint under the control. */
  sync_source: string;
  /** The folder most of the team's chart repos sit in (`<prefix><chart>.git`), or `null`. */
  repourl_prefix: string | null;
  known_sync_options: string[];
  scopes: ScopeReach[];
}

/** `GET /api/day2/fleet-defaults`: one `defaults/<scope>/<chart>/` folder. */
export interface FleetDefault {
  team: string;
  chart: string;
  scope: FleetScope;
  scope_label: string;
  path: string;
  /** The team has `operators/<chart>/` too. */
  in_catalog: boolean;
  /** `defaults/<scope>/<chart>/values.yaml`. */
  values: Record<string, unknown>;
  values_exists: boolean;
  /** Effective: the add-on's with the fleet layer on top. */
  sync: SyncSettings;
  /** The fleet layer (`defaults/<scope>/<chart>/<chart>.yaml`) sets `syncPolicy`. */
  sync_overridden: boolean;
  /** Destination ids it deploys to. */
  reach: string[];
  /** Destination ids `exclusions.yaml` keeps it off. */
  excluded: string[];
  /** The per-env and per-cluster value files (`values-<x>.yaml`). */
  tweaks: string[];
  last_commit_id: string | null;
  writable: boolean;
  read_only_reason: string | null;
  warnings: Finding[];
}

export interface GitLabInfo {
  gitlab_url: string;
  sigs_group_path: string;
  sigs_group_url: string;
}

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
  /** The stack layer `override_values` replaces (a fleet default's `values-<env>.yaml`); the cluster's own file when absent. */
  override_path?: string;
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

// ── Authoring: add-ons and fleet defaults (ADR-0043) ─────────────────────────

/** `POST /api/day2/addons/{team}`: a new add-on in the team's catalog. */
export interface CreateAddonBody {
  name: string;
  repourl: string;
  /** `null`: `HEAD`, the chart repo's default branch (no key written). */
  target_revision: string | null;
  /** `null`: `.` (no key written). */
  path: string | null;
  project_namespace: string | null;
  sync: SyncSettings;
  ignore_differences: unknown[] | null;
  values: Record<string, unknown>;
  /** Also make it a fleet default in the same MR. */
  default_scope: FleetScope | null;
  default_values: Record<string, unknown>;
  /** The preview's `needs_confirmation`, confirmed (ADR-0053). */
  confirm_changes?: string[];
  /** The preview's `digest`: the plan the user saw (ADR-0053). */
  expected_digest?: string | null;
  message: string | null;
}

/**
 * `PUT /api/day2/addons/{team}/{addon}`, Edit add-on (the API's team default,
 * hence the name): an absent field is unchanged; `null`
 * for `target_revision`, `path`, `project_namespace` or `ignore_differences`
 * removes that key.
 */
export interface UpdateTeamDefaultBody {
  repourl?: string;
  target_revision?: string | null;
  path?: string | null;
  project_namespace?: string | null;
  sync?: SyncSettings;
  ignore_differences?: unknown[] | null;
  values?: Record<string, unknown>;
  last_commit_id: string | null;
  confirm_changes?: string[];
  expected_digest?: string | null;
  message?: string | null;
}

/** `POST /api/day2/addons/{team}/{addon}/defaults/{scope}`. */
export interface MakeDefaultBody {
  values: Record<string, unknown>;
  /** `null`: inherit the add-on's. */
  sync: SyncSettings | null;
  /** Cluster ids, from a dry run's `needs_confirmation`. */
  confirm_changes: string[];
  expected_digest?: string | null;
  message: string | null;
}

/** `PUT /api/day2/addons/{team}/{addon}/defaults/{scope}`: absent fields are unchanged; `sync: null` inherits. */
export interface UpdateFleetDefaultBody {
  values?: Record<string, unknown>;
  sync?: SyncSettings | null;
  last_commit_id: string | null;
  confirm_changes?: string[];
  expected_digest?: string | null;
  message?: string | null;
}

export type AuthoringAction =
  | "create-addon"
  | "update-team-default"
  | "make-default"
  | "update-fleet-default"
  | "set-exclusions"
  | "override-values"
  | "override-deploy"
  | (string & {});

/** A file a dry run would write: `content` the new text (`null` for a delete), `previous` the current one. */
export interface PlannedFileChange {
  action: "create" | "update" | "delete" | (string & {});
  path: string;
  content: string | null;
  previous: string | null;
}

/** One key a move into a fleet default changes on a cluster. */
export interface AdoptionChange {
  stack: "deploy" | "values" | (string & {});
  /** A dotted leaf path, e.g. `syncPolicy.automated.prune`. */
  key: string;
  /** `null` when absent. */
  before: unknown;
  /** `null` when no longer set, or when set to a Helm null: `after_null` tells them apart. */
  after: unknown;
  /** The key is set to a Helm `null`: it deletes the chart's own default (ADR-0053). */
  after_null?: boolean;
}

/** A cluster whose own folder of the chart moves into the fleet default. */
export interface Adoption {
  cluster: string;
  name: string;
  moved: { from: string; to: string }[];
  deleted: string[];
  /** The `.gitkeep` that keeps the cluster registered, or `null`. */
  gitkeep: string | null;
  /** Empty: the move changes nothing on that cluster. */
  changes: AdoptionChange[];
  /** An old `exclusions.yaml` entry for the chart named it: removed in the same commit, or it would lose its app. */
  exclusion_removed?: boolean;
}

/** What a write does to the app of one destination (ADR-0053). */
export type ImpactEffect = "changed" | "removed" | "added" | (string & {});

/**
 * One destination whose app of the add-on changes, goes, or comes.
 * `changes` compare the effective deploy config and workload values before
 * and after, chart defaults aside; a `values` change with `after: null` is a
 * Helm null: it deletes the chart's own default for that key.
 */
export interface DestinationImpact {
  cluster: string;
  name: string;
  kind: DestinationKind | (string & {});
  effect: ImpactEffect;
  app_name: string | null;
  changes: AdoptionChange[];
  /** `removed` with `prune: false`: the Application goes, the workload keeps running, unmanaged. */
  orphaned: boolean;
}

/** What an authoring write's `?dry_run=true` answers: everything it would do, nothing opened. */
export interface AuthoringPlan {
  team: string;
  action: AuthoringAction;
  chart: string;
  scope: FleetScope | null;
  /** The MR title it would open. */
  title: string;
  files: PlannedFileChange[];
  reach: string[];
  adopted: Adoption[];
  /**
   * Every destination to confirm: each `removed` and `changed` one of
   * `impact`, and each `adopted` one whose move changes something. Sent back,
   * exactly, in `confirm_changes`.
   */
  needs_confirmation: string[];
  warnings: Finding[];
  notes: string[];
  /** Every destination whose app of this add-on changes, goes, or comes (ADR-0053). */
  impact: DestinationImpact[];
  /** The scope's destinations the default skips, after the change. */
  excluded: string[];
  /** sha256 of what the MR writes and does: sent back in `expected_digest`. */
  digest: string;
}

/** An authoring write's answer: the opened MR plus what it does. */
export interface AuthoringChange extends Day2MergeRequest {
  action: AuthoringAction;
  chart: string;
  scope: FleetScope | null;
  files: FileChange[];
  reach: string[];
  adopted: Adoption[];
  warnings: Finding[];
  notes: string[];
  needs_confirmation?: string[];
  impact?: DestinationImpact[];
  excluded?: string[];
  digest?: string;
}

// ── An add-on's defaults and overrides (ADR-0053) ────────────────────────────
// An add-on is a chart in a team's catalog (`operators/<chart>/` in the team
// repo) and the fleet defaults built from it (`defaults/<scope>/<chart>/`).
// docs/notes/2026-11-12-operators-page-api.md.

/** A file of the team repo, as read. Send `last_commit_id` back on an edit of it. */
export interface RepoFile {
  path: string;
  exists: boolean;
  /** The file's text, comments included; `null` when absent. */
  text: string | null;
  /** Parsed; `{}` when absent or invalid. */
  values: Record<string, unknown>;
  /** The commit the file was read at. */
  last_commit_id: string | null;
  /** The YAML error, if any. */
  problem: string | null;
}

/** A scope the add-on is a default on, in the add-ons list. */
export interface AddonDefaultSummary {
  scope: FleetScope;
  label: string;
  /** How many destinations it deploys to. */
  reach: number;
  /** How many `exclusions.yaml` keeps it off. */
  excluded: number;
}

/** `GET /api/day2/teams/{team}/addons`: one per `operators/<chart>/`, plus each fleet default without one. */
export interface AddonSummary {
  team: string;
  name: string;
  in_catalog: boolean;
  /** "" when unknown. */
  repourl: string;
  target_revision: string;
  sync: SyncSettings;
  /** The `ocp-versions/<v>/` folders. */
  ocp_versions: string[];
  /** Only the scopes it is a default on. */
  defaults: AddonDefaultSummary[];
  /** Apps from clusters' own folders. */
  installed_on: number;
  /** How many findings. */
  warnings: number;
  writable: boolean;
  read_only_reason: string | null;
}

/** An `operators/<chart>/ocp-versions/<version>/` pin. */
export interface AddonOcpVersion {
  version: string;
  target_revision: string | null;
  deploy_config: RepoFile;
  values_file: RepoFile;
}

/**
 * Where a scope's destination stands with the add-on:
 * - `default`: the default deploys it here;
 * - `excluded`: `exclusions.yaml` keeps the default off it, no app;
 * - `own-deploy`: excluded, and deployed from its own folder with its own deploy config (the platform's carve-out);
 * - `own-folder`: not a default on this scope; the cluster has the chart in its own folder;
 * - `duplicate`: a default and its own folder, not excluded: the platform generates the app twice (an error);
 * - `none`: not a default, no own folder;
 * - `not-rendered`: the platform renders nothing for it (day1 has no version for it).
 */
export type DestinationState =
  | "default"
  | "excluded"
  | "own-deploy"
  | "own-folder"
  | "duplicate"
  | "none"
  | "not-rendered"
  | (string & {});

/** One destination of a scope that the team's repo registers. */
export interface ScopeDestination {
  id: string;
  name: string;
  kind: DestinationKind;
  site: string;
  env: string;
  mce: string;
  ocp_version: string | null;
  /** False: day1 has no version for it, the platform renders nothing. */
  renders: boolean;
  state: DestinationState;
  /** An app of this add-on exists there. */
  deployed: boolean;
  app_name: string | null;
  /** `defaults/<scope>/<op>/values-<name>.yaml`; `null` for the hub. */
  override: RepoFile | null;
  /** Other destinations with the same name, so the same override file. */
  override_shared_with: string[];
  /** Its own `<op>/` folder, when it has one. */
  own_folder: string | null;
  /** `<own_folder>/<chart>.yaml`, when it has an own folder. */
  own_deploy: RepoFile | null;
}

/** A destination day1 or another team knows, that this team's repo does not register. */
export interface UnregisteredDestination {
  id: string;
  name: string;
  site: string;
  env: string;
  mce: string;
}

/** A scope's `defaults/<scope>/exclusions.yaml`, as the add-on's entry reads. */
export interface ScopeExclusions {
  path: string;
  exists: boolean;
  /** This add-on's entry, as written. */
  names: string[];
  /** Names in it that are no destination of the team. */
  unknown_names: string[];
  /** False: Wingman cannot edit it in place (`problem` says why). */
  last_commit_id: string | null;
}

/** The add-on on one fleet scope: a default there or not, and every destination of that kind. */
export interface ScopePanel {
  scope: FleetScope;
  /** "every MCE". */
  label: string;
  /** "MCE(s)". */
  noun: string;
  is_default: boolean;
  /** `defaults/<scope>/<op>`. */
  folder: string;
  values_file: RepoFile;
  /** `defaults/<scope>/<op>/<chart>.yaml`: the sync override. */
  deploy_config: RepoFile;
  /** Effective, over the add-on's. */
  sync: SyncSettings;
  sync_overridden: boolean;
  /** The `values-<env>.yaml` files that exist (read-only). */
  env_files: { env: string; file: RepoFile }[];
  /** `null` for the hub (it has none). */
  exclusions: ScopeExclusions | null;
  destinations: ScopeDestination[];
  unregistered: UnregisteredDestination[];
  /** The commit the team repo was read at. */
  last_commit_id: string | null;
}

/** `GET /api/day2/teams/{team}/addons/{addon}`. */
export interface AddonDetail {
  team: string;
  name: string;
  in_catalog: boolean;
  writable: boolean;
  read_only_reason: string | null;
  /** As `GET /addons/{team}/{addon}`; `null` when not in the catalog. */
  catalog: CatalogEntry | null;
  /** `operators/<chart>/<chart>.yaml`. */
  deploy_config: RepoFile;
  /** `operators/<chart>/values.yaml`. */
  values_file: RepoFile;
  ocp_versions: AddonOcpVersion[];
  /** hosted-clusters, mces, hub, upi. */
  scopes: ScopePanel[];
  warnings: Finding[];
}


/** `PUT .../defaults/{scope}/destinations/{cluster}/values`: `values-<name>.yaml`; `null` deletes it. */
export interface DestinationValuesBody {
  values: Record<string, unknown> | null;
  /** `ScopeDestination.override.last_commit_id` (`null` when absent). */
  last_commit_id: string | null;
  confirm_changes: string[];
  expected_digest: string | null;
  message: string | null;
}

/** `POST /api/day2/addons/{team}/{addon}/mce-installs`: deploy it on specific MCEs, one MR per MCE. */
export interface MceInstallsBody {
  /** MCE ids, `mce:<site>:<env>:<mce>`. */
  clusters: string[];
  /** Each MCE's `in-cluster/<chart>/values.yaml`. */
  values: Record<string, unknown>;
  message: string | null;
}

/** One chosen MCE: planned (a dry run), opened, refused (with the rule) or failed. */
export interface MceInstall {
  cluster: string;
  name: string;
  status: "planned" | "opened" | "refused" | "failed";
  files: FileChange[];
  notes: string[];
  warnings: Finding[];
  merge_request: Day2MergeRequest | null;
  detail: string | null;
  rule: string | null;
}

export interface MceInstalls {
  team: string;
  chart: string;
  installs: MceInstall[];
}

