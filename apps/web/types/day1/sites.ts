// ── Sites and MCEs (read-only, ADR-0018) ────────────────────────────────────

export interface Mce {
  name: string;
  site: string;
  env: string | null;
  letter: string | null;
  follows_convention: boolean;
  naming_problems: string[];
  /** The MCE's values.yaml mastertag: the create form's OCP version default, when the MCE offers it. */
  default_mastertag: string | null;
  hub_version: string | null;
  cluster_count: number;
  /** Files in hostedClusters/ that break the MCE's ApplicationSet. */
  stray_files: string[];
  problems: string[];
}

/** `GET /api/day1/mces/{mce}/openshift-versions` (ADR-0034). */
export interface OpenShiftVersions {
  mce: string;
  /** The upgrade ladder's releases in the minors the MCE can host, newest first, bare (`4.20.44`). */
  versions: string[];
  /** Why `versions` is short or empty: a missing or broken file under the day1 repo's `upgrade/`. */
  problems: string[];
}
