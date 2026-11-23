/**
 * Scaling a cluster's NodePools through the platform's update-nodepool
 * workflow (ADR-0062): what Scale can change, a start and the cluster's run.
 * Part of `day1Api.clusters`. 501 FEATURE_DISABLED on all three while Scale
 * is off (DAY1_SCALE_NODEPOOLS=false, or day1 has no orchestrator). A start is
 * never retried (ADR-0006).
 *
 * `where` is the `?site=&mce=` query the cluster page reads the cluster with.
 */

import { api } from "@/lib/api-client";
import type { ScaleOptions, ScaleRun, StartScaleRequest } from "@/types";
import { clusterPath } from "./clusters";

export const scaleApi = {
  /** The cluster's NodePools from its day1 file, its hardware kinds and its flavor's locks. */
  scaleOptions: (name: string, where: string) => api.get<ScaleOptions>(`${clusterPath(name)}/scale${where}`),
  /** Starts update-nodepool: 202 with the run (409 SCALE_ALREADY_RUNNING while one, or an upgrade, runs). */
  startScale: (name: string, where: string, body: StartScaleRequest) =>
    api.post<ScaleRun>(`${clusterPath(name)}/scale${where}`, body),
  /** The cluster's newest run (404 NOT_FOUND when it never had one). */
  scaleRun: (name: string, where: string) => api.get<ScaleRun>(`${clusterPath(name)}/scale-run${where}`),
};
