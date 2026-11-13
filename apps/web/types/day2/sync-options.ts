import type { Finding } from "./destinations";

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
