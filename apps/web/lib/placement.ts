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

import { useEffect, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api-client";
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
export const MAX_NEED_REPLICAS = 1000;

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
 * `GET /api/day1/placement?...` for `query`; empty parameters are left out, each
 * need is one `need`. With no need, an empty `need=` tells day1 the nodepools
 * name no node type yet, so it does not fall back to the flavor's presets.
 */
export function placementPath(query: PlacementQuery): string {
  const params = new URLSearchParams();
  const { needs = [], ...single } = query;
  for (const [key, value] of Object.entries(single)) if (value) params.set(key, value);
  for (const need of needs.length > 0 ? needs : [""]) params.append("need", need);
  return `/api/day1/placement?${params.toString()}`;
}

/**
 * The placement for `query`, read now (a few seconds' cache, never restored
 * from storage). While another query loads, the last answer stays as
 * placeholder data (`isPlaceholderData`), so the numbers do not flash away.
 */
export function usePlacement(query: PlacementQuery | null) {
  return useQuery<Placement>({
    queryKey: ["placement", query],
    queryFn: () => api.get<Placement>(placementPath(query!)),
    placeholderData: keepPreviousData,
    enabled: query !== null,
    staleTime: 5_000,
    refetchOnWindowFocus: true,
    retry: false,
  });
}

/** `value`, once it has stayed the same for `ms`. */
export function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
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
