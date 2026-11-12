/**
 * What a page shows for a cluster against its flavor (ADR-0044,
 * docs/notes/2026-11-12-flavor-rollout-api.md §1). Drift is measured against
 * the version the cluster's header names; a newer version of the flavor is an
 * update, never drift. In this order: drifted, unknown, an open update MR, an
 * update, in sync; a cluster that follows no flavor has none.
 */

import type { DriftState, FlavorUpdate } from "@/types";

export type FlavorDisplayState = "drifted" | "unknown" | "update_mr_open" | "update_available" | "in_sync" | "not_linked";

/** The fields of a drift row the display reads; `update` is absent from a day1 that predates it. */
export interface FlavorStateRow {
  state: DriftState;
  error?: string | null;
  /** The version the cluster's header names. */
  spec_version?: string | null;
  update?: FlavorUpdate | null;
}

/** The order the states are listed and counted in: what needs a person first. */
export const DISPLAY_ORDER: FlavorDisplayState[] = [
  "drifted",
  "unknown",
  "update_available",
  "update_mr_open",
  "in_sync",
  "not_linked",
];

export function flavorDisplayState(row: FlavorStateRow): FlavorDisplayState {
  if (row.state === "not_linked") return "not_linked";
  if (row.state === "drifted") return "drifted";
  if (row.state === "unknown") return "unknown";
  if (row.update?.merge_request) return "update_mr_open";
  if (row.update) return "update_available";
  return "in_sync";
}

const v = (version: string | null | undefined) => (version ? `v${version}` : null);

/** `v1.0.0 → v1.1.0`, or just the new one when the cluster's own version is not known. */
export function updateSpan(row: FlavorStateRow): string {
  const to = v(row.update?.version) ?? "";
  const from = v(row.spec_version);
  return from ? `${from} → ${to}` : to;
}

/** The badge's words: "Update MR open (v1.0.0 → v1.1.0)", "In sync · v1.0.0", "No flavor". */
export function flavorStateLabel(row: FlavorStateRow, state = flavorDisplayState(row)): string {
  switch (state) {
    case "drifted":
      return "Drifted";
    case "unknown":
      return "Unknown";
    case "update_mr_open":
      return `Update MR open (${updateSpan(row)})`;
    case "update_available":
      return `Update available (${updateSpan(row)})`;
    case "in_sync":
      return row.spec_version ? `In sync · v${row.spec_version}` : "In sync";
    case "not_linked":
      return "No flavor";
  }
}

/** The short name of a state, for counts and filters. */
export const STATE_NAME: Record<FlavorDisplayState, string> = {
  drifted: "Drifted",
  unknown: "Unknown",
  update_available: "Update available",
  update_mr_open: "Update MR open",
  in_sync: "In sync",
  not_linked: "No flavor",
};

/** What the state means, for a tooltip: always about the version the cluster is on. */
export function flavorStateHint(row: FlavorStateRow, state = flavorDisplayState(row)): string {
  const own = v(row.spec_version) ?? "its version of the flavor";
  const newest = v(row.update?.version);
  switch (state) {
    case "drifted":
      return `Against ${own}, the version it is on: a value it locks differs in the file, or an add-on it lists is not installed.${
        newest ? ` The flavor is at ${newest}.` : ""
      }`;
    case "unknown":
      return row.error || "Drift could not be determined";
    case "update_mr_open":
      return `!${row.update!.merge_request!.iid} moves it to ${newest}. Nothing changes on the cluster until it merges.`;
    case "update_available":
      return `In sync with ${own}. The flavor is at ${newest}, and no open merge request moves this cluster to it: the flavor's page says why.`;
    case "in_sync":
      return `The file holds every value ${own} locks, and every add-on it lists is installed.`;
    case "not_linked":
      return "The cluster follows no flavor, so there is nothing to drift from.";
  }
}
