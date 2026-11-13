import type { CatalogEntry } from "./catalog";
import type { DestinationKind, Finding } from "./destinations";
import type { FleetScope, SyncSettings } from "./sync-options";
import type { Day2MergeRequest, FileChange } from "./writes";

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
