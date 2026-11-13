/**
 * The review routes: the open MRs, one MR with its diff, an edit of its
 * files, approve and reject (ADR-0007: an MR is `(project, iid)`), and what
 * merging a flavor MR opens (ADR-0044).
 *
 * day2 answers the same routes, with the same shapes, for its team repos, and
 * the Approvals and Audit pages list both services under one cache namespace
 * (`approvals`, `audit` in keys.ts). So both services' review routes are here,
 * rather than one half in day2Api: `service` picks the one.
 *
 * Approve and an edit carry the head the reviewer saw (`sha`); a branch that
 * moved since is a 409, never retried (ADR-0006).
 */

import { api } from "@/lib/api-client";
import type { MRRef } from "@/lib/approvals";
import type { ApprovalDetail, ApprovalRollout, MRDetail, UpdateMRFile } from "@/types";

export type Service = "day1" | "day2";

/** day1 addresses an MR by iid and `?repo=` (day1 or specs); day2 by team and iid. */
function approvalPath(ref: MRRef, action?: "approve" | "reject"): string {
  const suffix = action ? `/${action}` : "";
  if (ref.service === "day2") {
    return `/api/day2/approvals/${encodeURIComponent(ref.team)}/${ref.iid}${suffix}`;
  }
  return `/api/day1/approvals/${ref.iid}${suffix}?repo=${ref.repo}`;
}

export const approvalsApi = {
  /** day1 lists the day1 and specs repos (each MR says which); day2 every team repo. */
  list: (service: Service) => api.get<MRDetail[]>(`/api/${service}/approvals`),
  detail: (ref: MRRef) => api.get<ApprovalDetail>(approvalPath(ref)),
  /** Commit edited files to the MR branch, refused if it moved past `sha`. */
  update: (ref: MRRef, body: { files: UpdateMRFile[]; message: string; sha: string }) =>
    api.put<ApprovalDetail>(approvalPath(ref), body),
  approve: (ref: MRRef, sha: string) => api.post<MRDetail>(approvalPath(ref, "approve"), { sha }),
  reject: (ref: MRRef) => api.post<MRDetail>(approvalPath(ref, "reject")),
  /** What merging an open specs MR opens, one MR per cluster. */
  rollout: (iid: number) => api.get<ApprovalRollout>(`/api/day1/approvals/${iid}/rollout?repo=specs`),
};
