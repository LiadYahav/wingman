/**
 * Live HostedCluster status from the MCE hubs. It is off unless the day1
 * service runs with CLUSTER_STATUS_ENABLED; then every status route answers
 * 501 FEATURE_DISABLED, which the app shows as "status is off", not an error.
 */

import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getToken, isApiError } from "@/lib/api-client";
import { day1Api, day1Keys } from "@/lib/api/day1";
import type { ClusterLiveStatus, ClusterPhase } from "@/types";

/** `null` when live status is off in this deployment. */
export type LiveStatuses = Record<string, ClusterLiveStatus> | null;

/** `bulk-status`: every requested cluster answers, with `error` set when its read failed. */
export async function fetchBulkStatus(clusters: { name: string; mce: string }[]): Promise<LiveStatuses> {
  try {
    return await day1Api.clusters.bulkStatus(clusters);
  } catch (error) {
    if (isApiError(error, "FEATURE_DISABLED")) return null;
    throw error;
  }
}

/** One cluster's status; `null` when live status is off. */
async function fetchLiveStatus(name: string, mce: string): Promise<ClusterLiveStatus | null> {
  try {
    return await day1Api.clusters.status(name, mce);
  } catch (error) {
    if (isApiError(error, "FEATURE_DISABLED")) return null;
    throw error;
  }
}

/**
 * One cluster's live status, read once (`null` when status is off), then
 * kept current by day1's server-sent stream while status is on.
 */
export function useClusterLiveStatus(name: string, mce: string) {
  const query = useQuery<ClusterLiveStatus | null>({
    queryKey: day1Keys.clusters.liveStatus(name, mce),
    queryFn: () => fetchLiveStatus(name, mce),
    enabled: Boolean(mce),
    staleTime: 30_000,
    retry: false,
  });
  useStatusStream(name, mce, query.data !== null && query.data !== undefined);
  return query;
}

/** A dropped stream is opened again this many times, waiting 5 s more each time (at most 30 s). */
const MAX_STREAM_RETRIES = 5;

/**
 * The status stream, once a first read showed status is on. fetch() instead
 * of EventSource, so the Authorization header can be sent. A status frame
 * replaces the cached status; an error frame ends the stream, and the last
 * status stays with its error.
 */
function useStatusStream(name: string, mce: string, statusOn: boolean) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!mce || !statusOn) return;
    const controller = new AbortController();
    const key = day1Keys.clusters.liveStatus(name, mce);
    const show = (frame: Partial<ClusterLiveStatus>) => {
      if (frame.cluster_name) queryClient.setQueryData(key, frame as ClusterLiveStatus);
      else if (frame.error) {
        queryClient.setQueryData<ClusterLiveStatus | null>(key, (prev) => prev && { ...prev, error: frame.error ?? null });
      }
    };
    let retries = 0;
    const startStream = async () => {
      try {
        const token = getToken();
        const res = await fetch(day1Api.clusters.statusStreamPath(name, mce), {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal: controller.signal,
        });
        if (!res.ok || !res.body) return;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const { frames, rest } = takeFrames(buffer + decoder.decode(value, { stream: true }));
          buffer = rest;
          frames.forEach(show);
        }
      } catch (e) {
        if ((e as Error).name !== "AbortError" && retries < MAX_STREAM_RETRIES) {
          retries++;
          setTimeout(startStream, Math.min(5_000 * retries, 30_000));
        }
      }
    };
    startStream();
    return () => controller.abort();
  }, [name, mce, statusOn, queryClient]);
}

/** The whole `data:` frames in a stream's buffer, and the partial event left for the next read. Malformed frames are dropped. */
function takeFrames(buffer: string): { frames: Partial<ClusterLiveStatus>[]; rest: string } {
  const events = buffer.split("\n\n");
  const rest = events.pop() ?? "";
  const frames = events.flatMap((event) => {
    const data = event.split("\n").find((line) => line.startsWith("data: "));
    if (!data) return [];
    try {
      return [JSON.parse(data.slice(6)) as Partial<ClusterLiveStatus>];
    } catch {
      return [];
    }
  });
  return { frames, rest };
}

export function liveStatusToPhase(s: ClusterLiveStatus): ClusterPhase {
  if (s.error) return "Error";
  if (s.hc_problems.length > 0) return "Error";
  if (s.node_pools.length === 0) return "Unknown";
  const allReady = s.node_pools.every(
    (np) => np.ready_replicas === np.desired_replicas && np.problems.length === 0
  );
  return allReady ? "Ready" : "Provisioning";
}
