import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { day1Keys } from "@/lib/api/day1";
import type { MRRef } from "@/lib/approvals";
import { day2Keys } from "@/lib/day2";
import { changedBy } from "./approval-changes";

const CLUSTER = "ocp4-prod-a-site1";
const HOSTED = "hosted:site1:prod:mce-a:ocp4-prod-a-site1";

/** One cached entry per read the review can touch, by a readable name. */
const READS: Record<string, readonly unknown[]> = {
  "day1 cluster": day1Keys.clusters.detail(CLUSTER),
  "day1 cluster list": day1Keys.clusters.all,
  "flavor": day1Keys.specs.one("web"),
  "flavor history": day1Keys.specs.history("web"),
  "day2 catalog": day2Keys.catalog,
  "day2 charts": day2Keys.charts(HOSTED),
  "day2 history": day2Keys.history(HOSTED),
  "day2 destinations": day2Keys.destinations,
  "day2 lints": day2Keys.lints,
  "day2 fleet defaults": day2Keys.fleetDefaults,
  "day2 team add-ons": day2Keys.teamAddons("redbull"),
  "day2 add-on": day2Keys.addonDetail("redbull", "bmhgen"),
  "day2 add-on template": day2Keys.addonTemplate("redbull"),
  "day2 merge preview": day2Keys.mergePreview(HOSTED, "redbull", "bmhgen", null),
  "day2 chart defaults": day2Keys.chartDefaults("redbull", "bmhgen", "1.0.0"),
  "day2 GitLab info": day2Keys.gitlabInfo,
  "day2 teams": day2Keys.teams,
};

/** The reads `changedBy(ref)` marks stale. */
async function invalidated(ref: MRRef): Promise<string[]> {
  const client = new QueryClient();
  for (const key of Object.values(READS)) client.setQueryData(key, "cached");
  await Promise.all(changedBy(ref).map((filters) => client.invalidateQueries(filters)));
  return Object.entries(READS)
    .filter(([, key]) => client.getQueryState(key)?.isInvalidated)
    .map(([name]) => name);
}

describe("changedBy", () => {
  it("a team's day2 MR refreshes the day2 reads of the team repos, and the clusters", async () => {
    expect(await invalidated({ service: "day2", team: "redbull", iid: 3 })).toEqual([
      "day1 cluster",
      "day1 cluster list",
      "day2 catalog",
      "day2 charts",
      "day2 history",
      "day2 destinations",
      "day2 lints",
      "day2 fleet defaults",
      "day2 team add-ons",
      "day2 add-on",
      "day2 add-on template",
      "day2 merge preview",
    ]);
  });

  it("a specs MR refreshes the flavors and their history, nothing of day2", async () => {
    expect(await invalidated({ service: "day1", repo: "specs", iid: 5 })).toEqual(["flavor", "flavor history"]);
  });

  it("a day1 MR refreshes the clusters, nothing of day2", async () => {
    expect(await invalidated({ service: "day1", repo: "day1", iid: 42 })).toEqual(["day1 cluster", "day1 cluster list"]);
  });
});
