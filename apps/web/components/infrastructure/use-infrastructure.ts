"use client";

import { useQuery } from "@tanstack/react-query";
import { day1Api, day1Keys } from "@/lib/api/day1";
import type { ClusterStatus, Mce } from "@/types";

/**
 * The two reads every Infrastructure page shares (ADR-0067), mounted under
 * `AdminsOnly` so a viewer never sends them: day1's MCE-level folders, each a
 * Customer MCE or a seed (an admin's read), and the clusters list, the
 * Clusters page's own cache entry.
 */
export function useMces() {
  return useQuery<Mce[]>({ queryKey: day1Keys.fleet.allMces, queryFn: day1Api.fleet.allMces, staleTime: 60_000 });
}

export function useAllClusters() {
  return useQuery<ClusterStatus[]>({ queryKey: day1Keys.clusters.all, queryFn: day1Api.clusters.list });
}
