"use client";

import { useQuery } from "@tanstack/react-query";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { useBulkStatus } from "@/hooks/use-bulk-status";
import { liveStatusToPhase } from "@/lib/live-status";
import { driftCounts, healthCounts } from "@/lib/overview/health";
import { newestFirst } from "@/lib/utils";
import { isKvCluster, tenantClusters } from "@/lib/workspaces";
import type { ClusterStatus, DriftSummaryItem, MRDetail, SpecEntry } from "@/types";

/**
 * The Overview's reads, one hook per source, so each card asks for what it
 * shows and loads, fails and empties on its own. The keys are the pages'
 * own (the Clusters, Flavors and Approvals pages), so the cache is shared:
 * two cards calling one hook make one request.
 */

/**
 * The tenants' clusters: the Customers workspace counts only theirs, so an
 * admin's KV clusters (ADR-0067) are left out here, as a viewer never has them.
 */
export function useOverviewClusters() {
  return useQuery<ClusterStatus[], Error, ClusterStatus[]>({
    queryKey: day1Keys.clusters.all,
    queryFn: day1Api.clusters.list,
    select: tenantClusters,
  });
}

/** The clusters' live phases from the MCE hubs: `off` when this deployment does not read them. */
export function useOverviewHealth() {
  const clusters = useOverviewClusters();
  const status = useBulkStatus(clusters.data);
  const list = clusters.data ?? [];
  const phases = list.flatMap((c) => {
    const live = status.data?.[c.name];
    return live ? [liveStatusToPhase(live)] : [];
  });
  return {
    clusters,
    status,
    health: healthCounts(list.length, phases),
    off: status.data === null,
    loading: clusters.isLoading || status.isLoading,
  };
}

export function useOverviewSpecs() {
  return useQuery<SpecEntry[]>({
    queryKey: day1Keys.specs.all,
    queryFn: day1Api.specs.list,
  });
}

export function useOverviewDrift() {
  const drift = useQuery<DriftSummaryItem[]>({
    queryKey: day1Keys.clusters.driftSummary,
    queryFn: day1Api.clusters.driftSummary,
    staleTime: 60_000, // drift asks day2 about every linked cluster
    gcTime: 5 * 60_000,
  });
  // The tenants' drift only: an admin's summary has the KV clusters' too (ADR-0067)
  const kv = useKvClusterNames();
  const rows = drift.data?.filter((d) => !kv.has(d.name));
  return { drift, counts: driftCounts(rows) };
}

const kvNames = (clusters: ClusterStatus[]) => new Set(clusters.filter(isKvCluster).map((c) => c.name));

/** The KV clusters' names, from the clusters list (an admin's; a viewer's has none). */
function useKvClusterNames(): Set<string> {
  const read = useQuery<ClusterStatus[], Error, Set<string>>({
    queryKey: day1Keys.clusters.all,
    queryFn: day1Api.clusters.list,
    select: kvNames,
  });
  return read.data ?? new Set();
}

function useApprovals(service: "day1" | "day2") {
  return useQuery<MRDetail[]>({
    queryKey: day1Keys.approvals.list(service),
    queryFn: () => day1Api.approvals.list(service),
    staleTime: 60_000,
  });
}

/** Both services' open MRs, newest first. */
export function useOverviewApprovals() {
  const day1 = useApprovals("day1");
  const day2 = useApprovals("day2");
  const all = newestFirst([day1.data, day2.data], (mr) => mr.created_at);
  return {
    day1Error: day1.error,
    day2Error: day2.error,
    recent: all.slice(0, 6),
    total: all.length,
    // Until both sources answered (or failed), a count or "all caught up" would be one source's.
    loading: day1.isPending || day2.isPending,
    unavailable: [day1.error && "day1", day2.error && "day2"].filter(Boolean) as string[],
    // Neither source answered: there is no count to show, not a count of zero.
    allFailed: Boolean(day1.error && day2.error),
  };
}
