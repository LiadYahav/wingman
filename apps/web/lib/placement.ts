/**
 * MCE placement (docs/notes/2026-11-12-mce-placement-api.md, ADR-0050): Wingman
 * picks the MCE for a new hosted cluster from the site, the environment, the
 * OpenShift version and the owner, and says why. The rule is day1's; the form
 * only shows its answer and sends the choice back, which day1 checks again.
 *
 * Placement always answers. With the MCE hubs' live reads off (`live_reads`
 * false), free pods and servers are `not_checked`, which does not block the
 * pick. The form has no MCE select of its own: a read that fails is a problem
 * with a retry.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { isApiError } from "@/lib/api-client";
import { day1Api, day1Keys } from "@/lib/api/day1";
import type { Placement, PlacementCandidate, PlacementCheck } from "@/types";

/** The environments a new cluster can be created in. */
export const PLACEMENT_ENVS = ["prod", "prep"] as const;
export type PlacementEnv = (typeof PLACEMENT_ENVS)[number];

/** The longest reason an admin may give for choosing another MCE than the pick. */
export const REASON_MAX = 500;

const OWNER = /^[0-9]{1,10}$/;
/** An InfraEnv is a Kubernetes name: one DNS-1123 label. */
const INFRA_ENV = /^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$/;
/** The replicas day1 accepts in a need. */
const MAX_NEED_REPLICAS = 1000;

/**
 * What the form asks placement about. Only a valid owner (1 to 10 digits) is
 * sent; `needs` are `<infra_env>:<replicas>`, one per nodepool (day1 sums a type).
 */
export interface PlacementQuery {
  site: string;
  env: string;
  version?: string;
  owner?: string;
  flavor?: string;
  needs?: string[];
}

/** The owner to rank by: the mador as typed, when it is a number day1 accepts; else none. */
export function placementOwner(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined;
  const text = String(value).trim();
  return OWNER.test(text) ? text : undefined;
}

/**
 * The servers the new cluster needs, as `need` values: one per nodepool that
 * names an InfraEnv (a DNS label) with 1 to 1000 replicas, in the form's order.
 * A nodepool still being filled in is left out until it is both.
 */
export function placementNeeds(nodepools: unknown): string[] {
  if (!Array.isArray(nodepools)) return [];
  const needs: string[] = [];
  for (const pool of nodepools) {
    if (!pool || typeof pool !== "object" || Array.isArray(pool)) continue;
    const { infra_env: infraEnv, replicas } = pool as Record<string, unknown>;
    const name = typeof infraEnv === "string" ? infraEnv.trim() : "";
    const count = typeof replicas === "number" ? replicas : /^\d+$/.test(String(replicas ?? "").trim()) ? Number(replicas) : NaN;
    if (INFRA_ENV.test(name) && Number.isInteger(count) && count >= 1 && count <= MAX_NEED_REPLICAS) {
      needs.push(`${name}:${count}`);
    }
  }
  return needs;
}

/**
 * The placement for `query`, read now (a few seconds' cache, never restored
 * from storage). While another query loads, the last answer stays as
 * placeholder data (`isPlaceholderData`), so the numbers do not flash away.
 */
export function usePlacement(query: PlacementQuery | null) {
  return useQuery<Placement>({
    queryKey: day1Keys.placement.query(query),
    queryFn: () => day1Api.fleet.placement(query!),
    placeholderData: keepPreviousData,
    enabled: query !== null,
    staleTime: 5_000,
    refetchOnWindowFocus: true,
    retry: false,
  });
}

/** A 409 from preview or create because Wingman's pick changed since the form showed it: the new pick. */
export function changedPick(error: unknown): string | null {
  if (!isApiError(error, "REVISION_CONFLICT")) return null;
  const pick = error.details.pick;
  return typeof pick === "string" && pick ? pick : null;
}

/** The checks a candidate does not pass, and those not known. */
export function unmetChecks(candidate: PlacementCandidate): PlacementCheck[] {
  return candidate.checks.filter((c) => c.status === "fail" || c.status === "unknown");
}

/** The checks Wingman did not make (live MCE reads are off); they do not block the pick. */
export function notCheckedChecks(candidate: PlacementCandidate): PlacementCheck[] {
  return candidate.checks.filter((c) => c.status === "not_checked");
}

/** What a check is called where a person reads it. */
export const CHECK_NAMES: Record<PlacementCheck["check"], string> = {
  version: "the version",
  free_pods: "free pods",
  servers: "servers",
  readable: "the MCE's API",
};

/**
 * Why a candidate cannot be chosen, in a few words for its row ("no 4.18.22",
 * "40 free pods", "1 of 2 servers"): its first failed check, else what is
 * unknown. `null` for a candidate that can be chosen. The full reasons are the
 * checks' own sentences.
 */
export function shortReason(candidate: PlacementCandidate, version: string | null): string | null {
  if (candidate.eligible) return null;
  const unmet = unmetChecks(candidate);
  const failed = unmet.find((check) => check.status === "fail");
  switch (failed?.check) {
    case "version":
      return version ? `no ${version}` : "not this version";
    case "free_pods":
      return candidate.pods ? `${candidate.pods.free} free pods` : "too few free pods";
    case "servers": {
      const type = candidate.node_types.find((t) => t.status === "fail");
      const free = type ? (type.healthy ?? type.free_agents) : null;
      return type && free !== null ? `${free} of ${type.needed} servers` : "too few servers";
    }
    case "readable":
      return "not readable";
  }
  if (unmet.some((check) => check.check === "readable")) return "not readable";
  return unmet.length > 0 ? `${SHORT_NAMES[unmet[0].check]} unknown` : null;
}

const SHORT_NAMES: Record<PlacementCheck["check"], string> = {
  version: "version",
  free_pods: "free pods",
  servers: "servers",
  readable: "API",
};

/** What a ranking step is called where a person reads it. */
export const BEHIND_ON: Record<NonNullable<PlacementCandidate["behind_on"]>, string> = {
  owner_clusters: "more clusters of this owner",
  clusters: "more clusters",
  spare_servers: "fewer usable spare servers",
  name: "same numbers; after the pick by name",
};

/** The reason as day1 records it: one line, trimmed. */
export function cleanReason(text: string): string {
  return text.replace(/\s*[\r\n]+\s*/g, " ").trim();
}
