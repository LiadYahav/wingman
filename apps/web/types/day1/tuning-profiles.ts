/**
 * `GET /api/day1/tuning-profiles`: the tuning profiles a nodepool can name,
 * from `tuning/` in the day1 repo (ADR-0061,
 * docs/notes/2026-11-15-tuning-profiles-api.md §1).
 */

/** A shared profile, `tuning/<name>.yaml`: the only names a flavor or a create may use. */
export interface TuningProfile {
  name: string;
  kind: "Tuned" | "PerformanceProfile";
  /** A Tuned's `[main]` `summary=`; `null` for a PerformanceProfile or a Tuned without one. */
  summary: string | null;
  path: string;
  /** The clusters (the chart's names) with a variant `tuning/<cluster>/<name>.yaml`. */
  clusters: string[];
  /**
   * For a Tuned that includes `openshift-node-performance-<pp>`: `<pp>`, the
   * PerformanceProfile it builds on; `null` otherwise (always for a PerformanceProfile).
   */
  requires_performance_profile: string | null;
}

/** A file in `tuning/` that is not offered, and why. */
export interface TuningProblem {
  path: string;
  detail: string;
}

export interface TuningProfiles {
  folder: string;
  /** `false`: the day1 repo has no `tuning/`; nothing is offered. */
  found: boolean;
  profiles: TuningProfile[];
  problems: TuningProblem[];
}
