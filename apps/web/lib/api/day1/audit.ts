/**
 * The audit routes of both services, for the Audit page: the commits and
 * MRs of every repo, and a commit's diff (an MR's is its approval detail).
 * As with the review routes (approvals.ts), day2 answers the same shapes and
 * the page keeps both under one `audit` namespace.
 */

import { api } from "@/lib/api-client";
import type { CommitRecord, FileDiff, MRDetail } from "@/types";
import type { Service } from "./approvals";

/** day1 serves the day1 and specs repos (by repo); day2 finds the team repo, hinted by team. */
function commitDiffPath(commit: CommitRecord): string {
  return commit.repo === "day2"
    ? `/api/day2/audit/commits/${commit.id}/diff${commit.team ? `?team=${encodeURIComponent(commit.team)}` : ""}`
    : `/api/day1/audit/commits/${commit.repo}/${commit.id}/diff`;
}

export const auditApi = {
  commits: (service: Service) => api.get<CommitRecord[]>(`/api/${service}/audit/commits`),
  mergeRequests: (service: Service) => api.get<MRDetail[]>(`/api/${service}/audit/merge-requests`),
  commitDiff: (commit: CommitRecord) => api.get<FileDiff[]>(commitDiffPath(commit)),
};
