// ── Drift ───────────────────────────────────────────────────────────────────

/** `unknown`: day2 did not answer or the spec is gone (`error` says which). */
export type DriftState = "in_sync" | "drifted" | "unknown" | "not_linked";

/** A spec addon the cluster does not have: the drift. The fix installs it at the add-on's revision. */
export interface AddonDrift {
  addon_name: string;
  team: string;
  reason: "missing";
  expected_version: string;
  /** The values requested at create; install with them. */
  override_values: Record<string, unknown>;
}

/** A spec addon installed at another version: information, never drift (ADR-0025). */
export interface VersionDifference {
  addon_name: string;
  team: string;
  spec_version: string;
  installed_version: string;
}

/** A nodepool of the cluster file: its position and the NodePool the chart renders. */
export interface NodepoolRef {
  index: number;
  name: string;
}

/** A locked value the cluster file does not hold (§10, ADR-0036). */
export interface ValueDrift {
  /** The flavor's lock: `owner_anaf`, `nodepools[0].configs` or the rule `nodepools[*].configs`. */
  path: string;
  /** Where the file holds it: `owner.anaf`, `nodepool[1].configs`. */
  file_key: string;
  nodepool: NodepoolRef | null;
  /** The locked value in the file's form; `nm-conf` expanded where the nodepool's hardware is known. */
  flavor_value: unknown;
  /** What the file holds; `null` with `in_file: false` when the key is absent. */
  cluster_value: unknown;
  in_file: boolean;
  /** Configs only: the names a sync adds. */
  added: string[];
  /** Configs only: the names a sync removes. */
  removed: string[];
  /** Why a sync cannot set this value until a person decides; `null` when it can. */
  needs_decision: string | null;
  /** The decision is the nodepool's network hardware type: a sync request can choose it. */
  needs_hardware: boolean;
  /** A nodepool's configs: syncing them rolls its nodes. */
  reboots: boolean;
}

/**
 * An open merge request as day1 links it (ADR-0007: an MR is `(project, iid)`);
 * a rollout's MRs are in the day1 repo. Its review page is `approvalHref(link)`.
 */
export interface MergeRequestLink {
  repo: "day1";
  iid: number;
  title: string;
  web_url: string;
}

/**
 * A newer version of the cluster's flavor than the one its header names
 * (ADR-0044, docs/notes/2026-11-12-flavor-rollout-api.md §1): an update,
 * never drift. `null` on a row when the cluster is on the newest version, or
 * the newest cannot be read.
 */
export interface FlavorUpdate {
  /** The flavor's newest version. */
  version: string;
  /** The open MR that moves this cluster to `version`, if there is one. */
  merge_request: MergeRequestLink | null;
}

/**
 * `GET /clusters/{name}/drift`. Drifted: a locked value differs, or an add-on
 * is missing, against the version of the flavor the cluster's header names
 * (`spec_version`), never the newest (ADR-0044).
 */
export interface ClusterDrift {
  cluster: string;
  site: string;
  mce: string;
  state: DriftState;
  /** `null` when unknown. */
  is_drifted: boolean | null;
  spec_name: string | null;
  /** The version the header names: what drift compares with. */
  spec_version: string | null;
  /** The flavor's newest version. */
  current_spec_version: string | null;
  value_drift: ValueDrift[];
  addon_drift: AddonDrift[];
  version_differences: VersionDifference[];
  error: string | null;
  update: FlavorUpdate | null;
}

/** A row of `GET /clusters/drift-summary`. */
export interface DriftSummaryItem {
  name: string;
  site: string;
  mce: string;
  state: DriftState;
  is_drifted: boolean | null;
  error: string | null;
  spec_name: string | null;
  /** The version the header names. */
  spec_version: string | null;
  update: FlavorUpdate | null;
}

/** A row of `GET /specs/{name}/clusters`. */
export interface SpecCluster {
  name: string;
  site: string;
  mce: string;
  phase: string;
  state: DriftState;
  is_drifted: boolean | null;
  error: string | null;
  /** The version the header names. */
  spec_version: string | null;
  update: FlavorUpdate | null;
}

/** A row of `GET /specs/{name}/drift`. */
export interface SpecDrift {
  cluster: string;
  site: string;
  mce: string;
  state: DriftState;
  is_drifted: boolean | null;
  spec_version: string | null;
  error: string | null;
  update: FlavorUpdate | null;
}
