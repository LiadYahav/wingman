import type { DestinationKind, Finding } from "./destinations";
import type { FleetScope, SyncSettings } from "./sync-options";
import type { Day2MergeRequest, FileChange } from "./writes";

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
