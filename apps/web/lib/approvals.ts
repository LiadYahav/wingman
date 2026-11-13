/**
 * How the web app addresses a merge request (ADR-0007: an MR is `(project, iid)`).
 *
 * - day1 service: the day1 values repo or the specs repo, by `?repo=` (day1 is
 *   the default), so `day1-<iid>` / `specs-<iid>`.
 * - day2 service: one repo per team, so `day2-<team>-<iid>`. A team name is a
 *   DNS label and may contain dashes; the iid is the last segment.
 */

import type { MRDetail } from "@/types";

export type MRRef =
  | { service: "day1"; repo: "day1" | "specs"; iid: number }
  | { service: "day2"; team: string; iid: number };

export function mrRef(mr: Pick<MRDetail, "repo" | "iid" | "team">): MRRef {
  if (mr.repo === "day2") return { service: "day2", team: mr.team ?? "", iid: mr.iid };
  return { service: "day1", repo: mr.repo, iid: mr.iid };
}

/** The `/approvals/[id]` segment for an MR. */
function approvalId(ref: MRRef): string {
  return ref.service === "day2" ? `day2-${ref.team}-${ref.iid}` : `${ref.repo}-${ref.iid}`;
}

export function approvalHref(mr: Pick<MRDetail, "repo" | "iid" | "team">): string {
  return `/approvals/${approvalId(mrRef(mr))}`;
}

const DAY1_ID = /^(day1|specs)-(\d+)$/;
const DAY2_ID = /^day2-([a-z0-9](?:[-a-z0-9]*[a-z0-9])?)-(\d+)$/;

/** Parse an `/approvals/[id]` segment; `null` if it is not one. */
export function parseApprovalId(id: string): MRRef | null {
  const day1 = DAY1_ID.exec(id);
  if (day1) return { service: "day1", repo: day1[1] as "day1" | "specs", iid: Number(day1[2]) };
  const day2 = DAY2_ID.exec(id);
  if (day2) return { service: "day2", team: day2[1], iid: Number(day2[2]) };
  return null;
}

/** The service route for an MR, optionally one of its actions. */
export function approvalApiPath(ref: MRRef, action?: "approve" | "reject"): string {
  const suffix = action ? `/${action}` : "";
  if (ref.service === "day2") {
    return `/api/day2/approvals/${encodeURIComponent(ref.team)}/${ref.iid}${suffix}`;
  }
  return `/api/day1/approvals/${ref.iid}${suffix}?repo=${ref.repo}`;
}

/** A stable key for lists and query caches. */
export function mrKey(mr: Pick<MRDetail, "repo" | "iid" | "team">): string {
  return approvalId(mrRef(mr));
}
