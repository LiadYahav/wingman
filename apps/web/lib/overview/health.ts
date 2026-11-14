/**
 * The Overview's counts of what the dashboard already read: the clusters'
 * live phases, the drift summary and the pending approvals. Pure: the cards
 * read the data, these only count it.
 */

import type { ClusterPhase, DriftSummaryItem } from "@/types";

export interface HealthCounts {
  ready: number;
  provisioning: number;
  error: number;
  /** No live status, or one that says nothing yet (`Unknown`). */
  unknown: number;
}

/**
 * `total` clusters, of which `phases` have a live status: a cluster without
 * one is Unknown, as is a status that names no NodePool yet.
 */
export function healthCounts(total: number, phases: readonly ClusterPhase[]): HealthCounts {
  const count = (phase: ClusterPhase) => phases.filter((p) => p === phase).length;
  return {
    ready: count("Ready"),
    provisioning: count("Provisioning"),
    error: count("Error"),
    unknown: total - phases.length + count("Unknown"),
  };
}

export interface DriftCounts {
  drifted: number;
  /** What else the summary says, e.g. `2 unknown · 1 with an update`; `""` when nothing. */
  hint: string;
}

/**
 * Against the version each cluster is on (ADR-0044): a newer flavor version
 * is an update, never drift.
 */
export function driftCounts(summary: readonly DriftSummaryItem[] | undefined): DriftCounts {
  const items = summary ?? [];
  const unknown = items.filter((d) => d.state === "unknown").length;
  const withUpdate = items.filter((d) => d.state === "in_sync" && d.update).length;
  return {
    drifted: items.filter((d) => d.state === "drifted").length,
    hint: [unknown > 0 && `${unknown} unknown`, withUpdate > 0 && `${withUpdate} with an update`].filter(Boolean).join(" · "),
  };
}
