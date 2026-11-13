/**
 * day1's cluster routes (`/api/day1/clusters`): the list, one cluster's file
 * and what is read beside it, and the merge requests that change it.
 *
 * `where` is the `?site=&mce=` query a page reads the cluster with
 * (`clusterQuery` in lib/clusters.ts, or `""`); it is sent as given, so each
 * caller keeps the URL it always sent. Writes are never retried (ADR-0006):
 * they carry the read's `last_commit_id`.
 */

import { api } from "@/lib/api-client";
import type {
  ClusterDetail,
  ClusterDrift,
  ClusterLiveStatus,
  ClusterNetworkRead,
  ClusterPreview,
  ClusterStatus,
  CreateClusterRequest,
  DriftSummaryItem,
  MRDetail,
  ModifyClusterRequest,
  NameSuggestion,
  ProvisionRun,
  SpecCommit,
  SyncPreview,
  SyncPreviewRequest,
  SyncRequest,
} from "@/types";

export const CLUSTERS = "/api/day1/clusters";

/** `/api/day1/clusters/{name}`, the name encoded. */
export const clusterPath = (name: string) => `${CLUSTERS}/${encodeURIComponent(name)}`;

/** The cluster a live-status read or stream is for: `?mce=` is required. */
const onMce = (mce: string) => `?mce=${encodeURIComponent(mce)}`;

export const clustersApi = {
  list: () => api.get<ClusterStatus[]>(CLUSTERS),
  driftSummary: () => api.get<DriftSummaryItem[]>(`${CLUSTERS}/drift-summary`),
  /** Every cluster's live status in one request (501 FEATURE_DISABLED when status is off). */
  bulkStatus: (clusters: { name: string; mce: string }[]) =>
    api.post<Record<string, ClusterLiveStatus>>(`${CLUSTERS}/bulk-status`, { clusters }),
  status: (name: string, mce: string) => api.get<ClusterLiveStatus>(`${clusterPath(name)}/status${onMce(mce)}`),
  /** The server-sent status stream, read with fetch() so the Authorization header can be sent. */
  statusStreamPath: (name: string, mce: string) => `${clusterPath(name)}/status/stream${onMce(mce)}`,
  /** A free name for a flavor on a site and MCE (ADR-0040). */
  nameSuggestion: (params: Record<string, string>) =>
    api.get<NameSuggestion>(`${CLUSTERS}/name-suggestion?${new URLSearchParams(params).toString()}`),
  preview: (request: CreateClusterRequest) => api.post<ClusterPreview>(`${CLUSTERS}/preview`, request),
  /** The merge request, or the started provision-cluster run in workflow mode (ADR-0042). */
  create: (request: CreateClusterRequest) => api.post<MRDetail | ProvisionRun>(CLUSTERS, request),
  detail: (name: string, where: string) => api.get<ClusterDetail>(`${clusterPath(name)}${where}`),
  drift: (name: string, where: string) => api.get<ClusterDrift>(`${clusterPath(name)}/drift${where}`),
  /** The file's commits: day1's `CommitOut`, the shape `SpecCommit` mirrors. */
  history: (name: string, where: string) => api.get<SpecCommit[]>(`${clusterPath(name)}/history${where}`),
  network: (name: string, where: string) => api.get<ClusterNetworkRead>(`${clusterPath(name)}/network${where}`),
  modify: (name: string, where: string, body: ModifyClusterRequest) =>
    api.patch<MRDetail>(`${clusterPath(name)}${where}`, body),
  /** A delete MR, guarded by the commit the file was read at. */
  remove: (name: string, where: string, lastCommitId: string) =>
    api.del<MRDetail>(
      `${clusterPath(name)}${where ? `${where}&` : "?"}last_commit_id=${encodeURIComponent(lastCommitId)}`
    ),
  syncPreview: (name: string, where: string, body: SyncPreviewRequest) =>
    api.post<SyncPreview>(`${clusterPath(name)}/sync/preview${where}`, body),
  sync: (name: string, where: string, body: SyncRequest) => api.post<MRDetail>(`${clusterPath(name)}/sync${where}`, body),
};
