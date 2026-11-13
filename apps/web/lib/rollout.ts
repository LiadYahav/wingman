/**
 * A flavor's rollout (ADR-0044, docs/notes/2026-11-12-flavor-rollout-api.md
 * §2): a new version opens one day1 MR per cluster that follows the flavor on
 * an older one, and each customer merges theirs when ready. Day1 opens them
 * (after the flavor MR merges, on the specs webhook, on Reconcile now, and on
 * a read with work pending); the web reads where each cluster stands.
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { RolloutState, RolloutStatus } from "@/types";

/** How often a rollout that is opening MRs is read again. */
const ROLLOUT_POLL_MS = 3_000;

export function rolloutPath(spec: string): string {
  return `/api/day1/specs/${encodeURIComponent(spec)}/rollout`;
}

export const rolloutKey = (spec: string) => ["specs", spec, "rollout"] as const;

/** `GET /specs/{name}/rollout`, read again every 3 s while day1 is opening MRs, not otherwise. */
export function useRollout(spec: string, enabled = true) {
  return useQuery<RolloutStatus>({
    queryKey: rolloutKey(spec),
    queryFn: () => api.get<RolloutStatus>(rolloutPath(spec)),
    enabled,
    staleTime: 15_000,
    refetchInterval: (query) => (query.state.data?.running ? ROLLOUT_POLL_MS : false),
    refetchOnWindowFocus: false,
  });
}

/** The order states are counted and listed in: what needs a person first, what is done last. */
export const ROLLOUT_ORDER: RolloutState[] = [
  "needs_decision",
  "failed",
  "unknown",
  "declined",
  "pending",
  "merge_request_open",
  "on_version",
];

/** A state's name, for its count and its group. */
export const ROLLOUT_LABEL: Record<RolloutState, string> = {
  needs_decision: "Needs a decision",
  failed: "Failed",
  unknown: "Unknown",
  declined: "Declined",
  pending: "Pending",
  merge_request_open: "MR open",
  on_version: "On the version",
};

/** "12 MRs open · 1 needs a decision": the states that are not done, for a one-line summary. */
export function rolloutSummary(status: RolloutStatus): string {
  const parts: string[] = [];
  const n = (state: RolloutState) => status.counts[state] ?? 0;
  if (n("merge_request_open")) parts.push(`${n("merge_request_open")} MR${n("merge_request_open") === 1 ? "" : "s"} open`);
  if (n("pending")) parts.push(`${n("pending")} pending`);
  if (n("needs_decision")) parts.push(`${n("needs_decision")} need${n("needs_decision") === 1 ? "s" : ""} a decision`);
  if (n("declined")) parts.push(`${n("declined")} declined`);
  if (n("failed")) parts.push(`${n("failed")} failed`);
  if (n("unknown")) parts.push(`${n("unknown")} unknown`);
  return parts.join(" · ");
}
