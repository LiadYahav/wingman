import { describe, expect, it } from "vitest";
import { day1Keys } from "./keys";

/**
 * Each key equals, value for value, the literal the pages spelled before
 * 3.18.5 (the right column, as it was written there). TanStack matches by
 * value and by prefix, so an equal array keeps every invalidation, prefetch
 * and setQueryData hitting what it did.
 */
const name = "ocp4-prod-a-site1";
const input = [{ name, mce: "mce-prod-1" }];
const hardware = [{ nodepool: 0, hardware: "dell" }];
const query = { site: "site1", env: "prod", flavor: "web" };
const suggestFor = { site: "site1", mce: "mce-prod-1", flavor: "web" };

const cases: [string, readonly unknown[], unknown[]][] = [
  // clusters
  ["clusters.all", day1Keys.clusters.all, ["clusters"]],
  ["clusters.driftSummary", day1Keys.clusters.driftSummary, ["clusters", "drift-summary"]],
  ["clusters.bulkStatus", day1Keys.clusters.bulkStatus(input), ["clusters", "bulk-status", input]],
  ["clusters.provisioner", day1Keys.clusters.provisioner, ["clusters", "provisioner"]],
  ["clusters.one", day1Keys.clusters.one(name), ["clusters", name]],
  ["clusters.detail", day1Keys.clusters.detail(name), ["clusters", name, "detail"]],
  ["clusters.liveStatus", day1Keys.clusters.liveStatus(name, "mce-prod-1"), ["clusters", name, "live-status", "mce-prod-1"]],
  ["clusters.drift", day1Keys.clusters.drift(name), ["clusters", name, "drift"]],
  ["clusters.histories", day1Keys.clusters.histories(name), ["clusters", name, "history"]],
  ["clusters.history", day1Keys.clusters.history(name), ["clusters", name, "history", "day1"]],
  ["clusters.network", day1Keys.clusters.network(name), ["clusters", name, "network"]],
  ["clusters.nodes", day1Keys.clusters.nodes(name), ["clusters", name, "nodes"]],
  ["clusters.provisionRun", day1Keys.clusters.provisionRun(name), ["clusters", name, "provision-run"]],
  ["clusters.deleteWorkflow", day1Keys.clusters.deleteWorkflow(name), ["clusters", name, "delete-workflow"]],
  [
    "clusters.syncPreview",
    day1Keys.clusters.syncPreview(name, "?site=site1", hardware),
    ["clusters", name, "sync-preview", "?site=site1", hardware],
  ],
  ["clusters.upgradeRun", day1Keys.clusters.upgradeRun(name), ["clusters", name, "upgrade-run"]],
  ["clusters.upgradeTargets", day1Keys.clusters.upgradeTargets(name), ["clusters", name, "upgrade-targets"]],
  ["clusters.upgrades", day1Keys.clusters.upgrades, ["clusters", "upgrades"]],
  // specs
  ["specs.all", day1Keys.specs.all, ["specs"]],
  ["specs.one", day1Keys.specs.one("web"), ["specs", "web"]],
  ["specs.clusters", day1Keys.specs.clusters("web"), ["specs", "web", "clusters"]],
  ["specs.drift", day1Keys.specs.drift("web"), ["specs", "web", "drift"]],
  ["specs.rollout", day1Keys.specs.rollout("web"), ["specs", "web", "rollout"]],
  ["specs.templateSchema", day1Keys.specs.templateSchema, ["specs", "template-schema"]],
  ["specs.sharedTemplate", day1Keys.specs.sharedTemplate, ["specs", "shared-template"]],
  // Under the flavor since 3.19.1 (they were ["spec-history", n] and ["spec-at-sha", n, sha])
  ["specs.history", day1Keys.specs.history("web"), ["specs", "web", "history"]],
  ["specs.atSha", day1Keys.specs.atSha("web", "abc123"), ["specs", "web", "at-sha", "abc123"]],
  ["specs.atSha (none chosen)", day1Keys.specs.atSha("web", null), ["specs", "web", "at-sha", null]],
  // approvals
  ["approvals.all", day1Keys.approvals.all, ["approvals"]],
  ["approvals.list day1", day1Keys.approvals.list("day1"), ["approvals", "day1"]],
  ["approvals.list day2", day1Keys.approvals.list("day2"), ["approvals", "day2"]],
  ["approvals.detail", day1Keys.approvals.detail("specs-12"), ["approvals", "detail", "specs-12"]],
  [
    "approvals.rollout",
    day1Keys.approvals.rollout("specs-12", "abc123"),
    ["approvals", "detail", "specs-12", "rollout", "abc123"],
  ],
  // audit
  ["audit.all", day1Keys.audit.all, ["audit"]],
  ["audit.commits day1", day1Keys.audit.commits("day1"), ["audit", "day1", "commits"]],
  ["audit.commits day2", day1Keys.audit.commits("day2"), ["audit", "day2", "commits"]],
  ["audit.mergeRequests day1", day1Keys.audit.mergeRequests("day1"), ["audit", "day1", "mrs"]],
  ["audit.mergeRequests day2", day1Keys.audit.mergeRequests("day2"), ["audit", "day2", "mrs"]],
  ["audit.commitDiff", day1Keys.audit.commitDiff("specs", "abc123"), ["audit", "specs", "commit-diff", "abc123"]],
  ["audit.mrDiff", day1Keys.audit.mrDiff("day2-falcon-3"), ["audit", "mr-diff", "day2-falcon-3"]],
  // fleet
  ["fleet.sites", day1Keys.fleet.sites, ["sites"]],
  ["fleet.mcesAt", day1Keys.fleet.mcesAt("site1"), ["mces", "site1"]],
  ["fleet.allMces", day1Keys.fleet.allMces, ["mces", "all"]],
  ["fleet.infraEnvs", day1Keys.fleet.infraEnvs("mce-prod-1"), ["mce-infraenvs", "mce-prod-1"]],
  ["fleet.openshiftVersions", day1Keys.fleet.openshiftVersions("mce-prod-1"), ["mce-openshift-versions", "mce-prod-1"]],
  ["fleet.openshiftVersions (no MCE)", day1Keys.fleet.openshiftVersions(undefined), ["mce-openshift-versions", undefined]],
  ["fleet.machineConfigs", day1Keys.fleet.machineConfigs, ["machine-configs"]],
  ["fleet.quickLinks", day1Keys.fleet.quickLinks, ["quick-links"]],
  // placement and the rest
  ["placement.all", day1Keys.placement.all, ["placement"]],
  ["placement.query", day1Keys.placement.query(query), ["placement", query]],
  ["placement.query (none)", day1Keys.placement.query(null), ["placement", null]],
  ["nameSuggestion", day1Keys.nameSuggestion(suggestFor), ["name-suggestion", suggestFor]],
  ["nameSuggestion (none)", day1Keys.nameSuggestion(null), ["name-suggestion", null]],
  ["flavorClusterPreview", day1Keys.flavorClusterPreview('{"name":"x"}'), ["flavor-cluster-preview", '{"name":"x"}']],
  ["build day1", day1Keys.build("day1"), ["build", "/api/day1/build"]],
  ["build day2", day1Keys.build("day2"), ["build", "/api/day2/build"]],
];

describe("day1Keys", () => {
  it.each(cases)("%s equals the literal it replaces", (_label, key, literal) => {
    expect(key).toStrictEqual(literal);
  });

  it("keeps the prefixes the writes invalidate", () => {
    const startsWith = (key: readonly unknown[], prefix: readonly unknown[]) =>
      prefix.every((part, i) => key[i] === part);
    expect(startsWith(day1Keys.clusters.detail(name), day1Keys.clusters.one(name))).toBe(true);
    expect(startsWith(day1Keys.clusters.upgradeRun(name), day1Keys.clusters.one(name))).toBe(true);
    expect(startsWith(day1Keys.clusters.history(name), day1Keys.clusters.histories(name))).toBe(true);
    expect(startsWith(day1Keys.clusters.one(name), day1Keys.clusters.all)).toBe(true);
    expect(startsWith(day1Keys.specs.rollout("web"), day1Keys.specs.all)).toBe(true);
    expect(startsWith(day1Keys.approvals.list("day2"), day1Keys.approvals.all)).toBe(true);
    expect(startsWith(day1Keys.audit.mrDiff("x"), day1Keys.audit.all)).toBe(true);
    expect(startsWith(day1Keys.placement.query(query), day1Keys.placement.all)).toBe(true);
    // A flavor write, or a merged flavor MR, invalidates `specs.all`: its history is read again too
    expect(startsWith(day1Keys.specs.history("web"), day1Keys.specs.all)).toBe(true);
    expect(startsWith(day1Keys.specs.atSha("web", "abc123"), day1Keys.specs.all)).toBe(true);
    expect(startsWith(day1Keys.specs.history("web"), day1Keys.specs.one("web"))).toBe(true);
  });
});
