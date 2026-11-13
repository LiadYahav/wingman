/**
 * What approving (merging) or rejecting (closing) a merge request can change
 * besides the review lists, as the query filters to invalidate:
 *
 * - a day1 MR: the clusters (their files, and the open create MRs day1 lists);
 * - a specs MR: the flavors, their history included (day1Keys.specs.all);
 * - a team's day2 MR: every day2 read of the team repos (DAY2_TEAM_REPO_READS),
 *   and the clusters, since day1 shows the day2 installs open on a cluster.
 */

import type { InvalidateQueryFilters } from "@tanstack/react-query";
import { day1Keys } from "@/lib/api/day1";
import type { MRRef } from "@/lib/approvals";
import { DAY2_TEAM_REPO_READS } from "@/lib/day2";

export function changedBy(ref: MRRef): InvalidateQueryFilters[] {
  if (ref.service === "day2") return [{ queryKey: day1Keys.clusters.all }, DAY2_TEAM_REPO_READS];
  return [{ queryKey: ref.repo === "specs" ? day1Keys.specs.all : day1Keys.clusters.all }];
}
