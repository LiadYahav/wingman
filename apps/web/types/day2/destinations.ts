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
  /**
   * `hub`, `mce:<site>:<env>:<mce>`, `hosted:<site>:<env>:<mce>:<cluster>` or
   * `upi:<site>:<env>:<cluster>`; a viewer's is the hosted cluster's name (ADR-0068).
   */
  id: string;
  kind: DestinationKind;
  name: string;
  site: string;
  /** "" when no team repo or name gives one; such a destination cannot be written to. */
  env: string;
  /** `null` for a viewer, as `argo` (ADR-0068). */
  mce: string | null;
  ocp_version: string | null;
  /** The ArgoCD instance its leaf apps live on. */
  argo: string | null;
  teams: string[];
  in_day1: boolean;
  warnings: Finding[];
}
