import type { DestinationKind, Finding } from "./destinations";

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
