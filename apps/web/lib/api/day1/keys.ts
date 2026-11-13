/**
 * Every query key outside `day2` (lib/day2.ts) and the Segments and Inventory
 * areas (lib/api/segments.ts, inventory.ts), in one place. TanStack matches a
 * key by value and by prefix, so these arrays are exactly the ones the pages
 * spelled inline before 3.18.5: keys.test.ts holds each to its literal.
 *
 * The prefixes a write invalidates:
 * - `clusters.all`: every cluster read, the list and each cluster's;
 *   `clusters.one(name)` one cluster's (detail, drift, history, nodes, upgrade, ...).
 * - `specs.all`: the flavor list and each flavor's reads, but not their
 *   history (`spec-history`, `spec-at-sha` are their own namespaces).
 * - `approvals.all`, `audit.all`: both services' lists (approvals.ts says why
 *   both are here); the approval page leaves its own detail out by predicate.
 * - `placement.all`: every placement read.
 *
 * `drift-summary`, `bulk-status`, `provisioner` and `upgrades` sit where a
 * cluster's name does; cluster names follow `ocp4-<env>-<name>-<site>`, so
 * none collides.
 */

import type { PlacementQuery } from "@/lib/placement";
import type { HardwareChoice } from "@/types";
import type { Service } from "./approvals";

const clusters = {
  all: ["clusters"] as const,
  driftSummary: ["clusters", "drift-summary"] as const,
  bulkStatus: (input: { name: string; mce: string }[]) => ["clusters", "bulk-status", input] as const,
  provisioner: ["clusters", "provisioner"] as const,
  /** Every cluster's newest upgrade run: under `clusters.all`, so the list's Refresh reads it too. */
  upgrades: ["clusters", "upgrades"] as const,
  one: (name: string) => ["clusters", name] as const,
  detail: (name: string) => ["clusters", name, "detail"] as const,
  liveStatus: (name: string, mce: string) => ["clusters", name, "live-status", mce] as const,
  drift: (name: string) => ["clusters", name, "drift"] as const,
  /** Every history of the cluster (day1's file; day2's values are `day2Keys.history`). */
  histories: (name: string) => ["clusters", name, "history"] as const,
  history: (name: string) => ["clusters", name, "history", "day1"] as const,
  network: (name: string) => ["clusters", name, "network"] as const,
  nodes: (name: string) => ["clusters", name, "nodes"] as const,
  provisionRun: (name: string) => ["clusters", name, "provision-run"] as const,
  deleteWorkflow: (name: string) => ["clusters", name, "delete-workflow"] as const,
  syncPreview: (name: string, where: string, hardware: HardwareChoice[]) =>
    ["clusters", name, "sync-preview", where, hardware] as const,
  upgradeRun: (name: string) => ["clusters", name, "upgrade-run"] as const,
  upgradeTargets: (name: string) => ["clusters", name, "upgrade-targets"] as const,
};

const specs = {
  all: ["specs"] as const,
  one: (name: string) => ["specs", name] as const,
  clusters: (name: string) => ["specs", name, "clusters"] as const,
  drift: (name: string) => ["specs", name, "drift"] as const,
  rollout: (name: string) => ["specs", name, "rollout"] as const,
  templateSchema: ["specs", "template-schema"] as const,
  sharedTemplate: ["specs", "shared-template"] as const,
  history: (name: string) => ["spec-history", name] as const,
  atSha: (name: string, sha: string | null) => ["spec-at-sha", name, sha] as const,
};

const approvals = {
  all: ["approvals"] as const,
  list: (service: Service) => ["approvals", service] as const,
  /** `id` is the `/approvals/[id]` segment. */
  detail: (id: string) => ["approvals", "detail", id] as const,
  /** Under the detail's key: a change elsewhere does not read it again, a reload of the MR does. */
  rollout: (id: string, sha: string | undefined) => ["approvals", "detail", id, "rollout", sha] as const,
};

const audit = {
  all: ["audit"] as const,
  commits: (service: Service) => ["audit", service, "commits"] as const,
  mergeRequests: (service: Service) => ["audit", service, "mrs"] as const,
  /** `repo` is the commit's (day1, specs or day2). */
  commitDiff: (repo: string, id: string) => ["audit", repo, "commit-diff", id] as const,
  /** `mr` is `mrKey(mr)` (lib/approvals.ts). */
  mrDiff: (mr: string) => ["audit", "mr-diff", mr] as const,
};

const fleet = {
  sites: ["sites"] as const,
  mcesAt: (site: string) => ["mces", site] as const,
  /** Every MCE: `"all"` where a site's name goes (a follow-up: a site named `all` would share it). */
  allMces: ["mces", "all"] as const,
  infraEnvs: (mce: string) => ["mce-infraenvs", mce] as const,
  openshiftVersions: (mce: string | undefined) => ["mce-openshift-versions", mce] as const,
  machineConfigs: ["machine-configs"] as const,
  quickLinks: ["quick-links"] as const,
};

const placement = {
  all: ["placement"] as const,
  query: (query: PlacementQuery | null) => ["placement", query] as const,
};

export const day1Keys = {
  clusters,
  specs,
  approvals,
  audit,
  fleet,
  placement,
  /** The new-cluster form's name suggestion for `{site, mce, flavor}`. */
  nameSuggestion: (params: Record<string, string> | null) => ["name-suggestion", params] as const,
  /** The flavor editor's cluster-file preview, by the request's JSON. */
  flavorClusterPreview: (body: string) => ["flavor-cluster-preview", body] as const,
  build: (service: Service) => ["build", `/api/${service}/build`] as const,
};
