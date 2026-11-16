/**
 * Scaling a cluster's NodePools through the platform's update-nodepool
 * workflow (ADR-0062): what Scale can change, the cluster's run and a start.
 * Wingman starts the run and shows it; the plan and its checks are the
 * workflow's. Writes are never retried (ADR-0006): a refusal that says the
 * page is out of date reads the run again instead.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isApiError } from "@/lib/api-client";
import { day1Api, day1Keys } from "@/lib/api/day1";
import { useUpgradeRun } from "@/lib/api/upgrades";
import { busyReason, isRunning, STALE_RUN_CODES } from "@/lib/scale-model";
import { isOpen as isUpgradeOpen } from "@/lib/upgrade";
import type { ScaleOptions, ScaleRun, StartScaleRequest } from "@/types";

/** Scaling off (501 FEATURE_DISABLED: nothing is shown), or what it can change on the cluster. */
export type ScaleOptionsRead = { state: "off" } | { state: "on"; options: ScaleOptions };

/** Scaling off, on with no run yet (404), or the cluster's newest run. */
export type ScaleRunRead = { state: "off" } | { state: "none" } | { state: "run"; run: ScaleRun };

/** How often a running run is read again. */
const RUN_POLL_MS = 10_000;

/** `GET /clusters/{name}/scale{where}`: the day1 file's NodePools, its kinds and its flavor's locks. */
export function useScaleOptions(name: string, where: string, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery<ScaleOptionsRead>({
    queryKey: day1Keys.clusters.scaleOptions(name),
    queryFn: async () => {
      try {
        return { state: "on", options: await day1Api.clusters.scaleOptions(name, where) };
      } catch (e) {
        if (isApiError(e, "FEATURE_DISABLED")) return { state: "off" };
        throw e;
      }
    },
    enabled,
    staleTime: 10_000,
    retry: false,
  });
}

/**
 * `GET /clusters/{name}/scale-run{where}`, shared by the panel and every restore. Read again every 10 s while running.
 * When a run seen running has ended, the cluster's other reads (its sizes, its nodes) are read again.
 */
export function useScaleRun(name: string, where: string, { enabled = true }: { enabled?: boolean } = {}) {
  const queryClient = useQueryClient();
  const runKey = day1Keys.clusters.scaleRun(name);
  return useQuery<ScaleRunRead>({
    queryKey: runKey,
    queryFn: async () => {
      try {
        const before = queryClient.getQueryData<ScaleRunRead>(runKey);
        const run = await day1Api.clusters.scaleRun(name, where);
        if (before?.state === "run" && isRunning(before.run) && !isRunning(run)) {
          void queryClient.invalidateQueries({
            queryKey: day1Keys.clusters.one(name),
            predicate: (query) => query.queryKey[2] !== runKey[2],
          });
        }
        return { state: "run", run };
      } catch (e) {
        if (isApiError(e, "FEATURE_DISABLED")) return { state: "off" };
        if (isApiError(e, "NOT_FOUND")) return { state: "none" };
        throw e;
      }
    },
    enabled,
    staleTime: 10_000,
    retry: false,
    refetchInterval: (query) => {
      const read = query.state.data;
      return read?.state === "run" && isRunning(read.run) ? RUN_POLL_MS : false;
    },
  });
}

/**
 * Why a scale (or a restore) cannot start now, or `null`: a run of the
 * cluster is going, update-nodepool's or upgrade-cluster's. Both reads are
 * shared queries, so every button on the page waits on the same answer;
 * nothing is queued.
 */
export function useScaleBusy(name: string, where: string): string | null {
  const scale = useScaleRun(name, where);
  const upgrade = useUpgradeRun(name, where);
  const scaleRunning = scale.data?.state === "run" && isRunning(scale.data.run);
  const upgradeOpen = upgrade.data?.state === "run" && isUpgradeOpen(upgrade.data.run);
  return busyReason(scaleRunning, upgradeOpen);
}

/**
 * `POST /clusters/{name}/scale{where}`: a total over a kind's NodePools, or
 * one NodePool's replicas. Never retried. The started run shows at once; a
 * refusal that means a run is (or may be) going reads the run again.
 */
export function useStartScale(name: string, where: string) {
  const queryClient = useQueryClient();
  const runKey = day1Keys.clusters.scaleRun(name);
  return useMutation({
    mutationFn: (body: StartScaleRequest) => day1Api.clusters.startScale(name, where, body),
    onSuccess: (run) => queryClient.setQueryData<ScaleRunRead>(runKey, { state: "run", run }),
    onError: (error) => {
      if (STALE_RUN_CODES.some((code) => isApiError(error, code))) void queryClient.invalidateQueries({ queryKey: runKey });
    },
  });
}
