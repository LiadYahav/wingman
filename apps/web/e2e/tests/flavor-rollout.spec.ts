/**
 * A flavor's changes reach each cluster through its own MR (mocked; ADR-0044,
 * docs/notes/2026-11-12-flavor-rollout-api.md): a cluster is measured against
 * the version it is on and a newer one is an update, on the cluster list, the
 * flavor's clusters tab and the cluster's page (which links an open update MR
 * instead of offering a sync); the flavor's rollout (counts, each state with
 * its reasons and MRs, read again while day1 opens MRs, Reconcile now for
 * admins only); and, on a flavor MR's approve page, what merging it opens.
 */

import { test, expect, type Page, type Request, type Route } from "@playwright/test";
import {
  fulfillProblem, go, injectAdminAuth, json, mockApprovalRollout, mockDashboardApis, mockMergeRequestLink, mockMR, mockRollout,
  mockRolloutCluster,
} from "../fixtures/api-handlers";
import type {
  ApprovalDetail, ApprovalRollout, ClusterDetail, ClusterDrift, ClusterStatus, DestinationCharts, DriftState, DriftSummaryItem,
  FlavorUpdate, RolloutStatus, SpecCluster, SpecDetail, SyncPreview,
} from "../../types";

const FLAVOR = "agent-baseline";
const SITE = "site1";
const MCE = "ocp4-prod-mce-site1-a";
const LARK = "ocp4-prod-lark-site1";

const MR12 = mockMergeRequestLink(12, `[Wingman/Day1] Sync cluster ${LARK} to spec ${FLAVOR} v1.1.0`);
const UPDATE_OPEN: FlavorUpdate = { version: "1.1.0", merge_request: MR12 };
const UPDATE: FlavorUpdate = { version: "1.1.0", merge_request: null };

/** Each thing a page shows for a cluster that follows the flavor, one cluster each. */
const ROWS: {
  name: string; state: DriftState; spec_version: string; update: FlavorUpdate | null; error: string | null; label: string; display: string;
}[] = [
  { name: "ocp4-prod-owl-site1", state: "drifted", spec_version: "1.0.0", update: UPDATE, error: null, label: "Drifted", display: "drifted" },
  {
    name: "ocp4-prod-hawk-site1", state: "unknown", spec_version: "0.9.0", update: null,
    error: "the header names v0.9.0, which the specs repo's history does not have", label: "Unknown", display: "unknown",
  },
  { name: LARK, state: "in_sync", spec_version: "1.0.0", update: UPDATE_OPEN, error: null, label: "Update MR open (v1.0.0 → v1.1.0)", display: "update_mr_open" },
  { name: "ocp4-prod-heron-site1", state: "in_sync", spec_version: "1.0.0", update: UPDATE, error: null, label: "Update available (v1.0.0 → v1.1.0)", display: "update_available" },
  { name: "ocp4-prod-kite-site1", state: "in_sync", spec_version: "1.1.0", update: null, error: null, label: "In sync · v1.1.0", display: "in_sync" },
];
const UNLINKED = "ocp4-prod-wren-site1";

const SPEC: SpecDetail = {
  apiVersion: "wingman.io/v1",
  kind: "ClusterSpec",
  metadata: { name: FLAVOR, description: "Every nodepool gets the team's machine configs", version: "1.1.0", labels: {} },
  spec: {
    day1: { variables: [], structure: {}, locked_paths: ["owner_anaf"], template: "", values: { owner_anaf: "56" } },
    day2: { addons: [] },
  },
  load_error: null,
  load_problems: [],
  warnings: [],
  enforced_locks: ["owner_anaf"],
  last_commit_id: "aaaaaaaa11111111aaaaaaaa11111111aaaaaaaa",
};

function listItem(name: string, spec_version: string | null): ClusterStatus {
  const short = name.replace(/^ocp4-/, "");
  return {
    name, site: SITE, mce: MCE, phase: "Unknown", spec_name: spec_version ? FLAVOR : null, spec_version,
    created_by: "alice", created_at: "2026-11-07T10:00:00+00:00", mastertag: "4.16.27-x86_64",
    path: `sites/${SITE}/mces/${MCE}/hostedClusters/${name}.yaml`,
    hosted_cluster: { cluster_name: short, name: `ocp4-${short}`, namespace: `hcp-${short}` },
    naming: { follows_convention: true, env: "prod", short_name: short, sequence: null, problems: [] },
    owner: {}, problems: [],
  };
}

const viewer = (page: Page) =>
  page.addInitScript(() => {
    const state = { state: { user: { username: "vera", groups: ["wingman-viewers"], uid: "vera", full_name: "Vera Viewer", role: "viewer" }, isAuthenticated: true }, version: 0 };
    localStorage.setItem("wingman-auth", JSON.stringify(state));
  });

// ── Drift against the cluster's own version, and its update ─────────────────

test.describe("Each cluster against its own version", () => {
  test("the cluster list shows each state, links an open update MR, and filters updates", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await page.route("**/api/day1/clusters", (r) => json(r, [...ROWS.map((x) => listItem(x.name, x.spec_version)), listItem(UNLINKED, null)]));
    const summary: DriftSummaryItem[] = [
      ...ROWS.map((x) => ({
        name: x.name, site: SITE, mce: MCE, state: x.state, is_drifted: x.state === "unknown" ? null : x.state === "drifted",
        error: x.error, spec_name: FLAVOR, spec_version: x.spec_version, update: x.update,
      })),
      { name: UNLINKED, site: SITE, mce: MCE, state: "not_linked", is_drifted: false, error: null, spec_name: null, spec_version: null, update: null },
    ];
    await page.route("**/api/day1/clusters/drift-summary", (r) => json(r, summary));
    await go(page, "/clusters");

    for (const x of ROWS) {
      const badge = page.getByTestId(`cluster-row-${x.name}`).getByTestId("flavor-state");
      await expect(badge).toHaveText(x.label);
      await expect(badge).toHaveAttribute("data-state", x.display);
    }
    await expect(page.getByTestId(`cluster-row-${UNLINKED}`).getByTestId("flavor-state")).toHaveText("No flavor");
    // The open update MR is a link to its review page
    await expect(page.getByTestId(`cluster-row-${LARK}`).getByRole("link", { name: /^Update MR open/ })).toHaveAttribute("href", "/approvals/day1-12");
    // Unknown says why on hover, and is never in sync
    await page.getByTestId("cluster-row-ocp4-prod-hawk-site1").getByTestId("flavor-state").hover();
    await expect(page.getByText(ROWS[1].error!)).toBeVisible();

    // An update (open MR or not) is its own filter, never drift
    await expect(page.getByRole("button", { name: /^Drifted\s*1$/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /^In sync\s*1$/ })).toBeVisible();
    await page.getByRole("button", { name: /^Update\s*2$/ }).click();
    await expect(page.getByTestId(`cluster-row-${LARK}`)).toBeVisible();
    await expect(page.getByTestId("cluster-row-ocp4-prod-heron-site1")).toBeVisible();
    await expect(page.getByTestId("cluster-row-ocp4-prod-owl-site1")).toHaveCount(0);
    await expect(page.getByTestId("cluster-row-ocp4-prod-kite-site1")).toHaveCount(0);
  });

  test("the dashboard counts drift apart from updates", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await page.route("**/api/day1/clusters/drift-summary", (r) =>
      json(r, ROWS.map((x) => ({
        name: x.name, site: SITE, mce: MCE, state: x.state, is_drifted: x.state === "drifted", error: x.error,
        spec_name: FLAVOR, spec_version: x.spec_version, update: x.update,
      })))
    );
    await go(page, "/");

    const drifted = page.getByTestId("stat-drifted");
    await expect(drifted).toContainText("1");
    await expect(drifted).toContainText("1 unknown · 2 with an update");
  });

  test("the flavor's clusters tab shows each state against the version each is on", async ({ page }) => {
    const rows: SpecCluster[] = ROWS.map((x) => ({
      name: x.name, site: SITE, mce: MCE, phase: "Unknown", state: x.state, is_drifted: x.state === "drifted", error: x.error,
      spec_version: x.spec_version, update: x.update,
    }));
    await openFlavor(page, { clusters: rows });
    await page.getByRole("button", { name: /^Clusters/ }).click();

    for (const x of ROWS) {
      const badge = page.getByTestId(`spec-cluster-${x.name}`).getByTestId("flavor-state");
      await expect(badge).toHaveText(x.label);
      await expect(badge).toHaveAttribute("data-state", x.display);
    }
    await expect(page.getByTestId(`spec-cluster-${LARK}`).getByRole("link", { name: /^Update MR open/ })).toHaveAttribute(
      "href", "/approvals/day1-12"
    );
  });
});

// ── The cluster page ─────────────────────────────────────────────────────────

const PATH = `sites/${SITE}/mces/${MCE}/hostedClusters/${LARK}.yaml`;
const READ_AT = "8bc410218818998ff47e641db7e97007162c678f";
const DETAIL: ClusterDetail = {
  name: LARK, site: SITE, mce: MCE,
  yaml: `# specName: ${FLAVOR}\n# specVersion: 1.0.0\nowner:\n  anaf: "56"\nnodepool:\n  - replicas: 3\n`,
  gitlab_url: "https://gitlab.example.com/gitops-day1/platform-config/-/blob/main/x.yaml",
  path: PATH,
  last_commit_id: READ_AT,
  metadata: {
    spec_name: FLAVOR, spec_version: "1.0.0", created_by: "alice", created_at: "2026-11-07T10:00:00+00:00",
    site: SITE, mce: MCE, variables: {}, immutable_paths: [], requested_addons: [],
  },
  values: {
    owner: { anaf: "56" }, mastertag: "4.16.27-x86_64", platform: "agent",
    nodepools: [{ name: "prod-lark-site1-dell", infra_env_name: "dell", replicas: 3, allow_deletion: false, configs: [], node_labels: {}, tuning_config: null }],
    network: { vlan_id: 120, dhcp_network: "10.0.0.0", segment: "10.0.0.0/24" },
    cluster_name: null, automation_keys: [],
  },
  hosted_cluster: { cluster_name: "prod-lark-site1", name: "ocp4-prod-lark-site1", namespace: "hcp-prod-lark-site1" },
  naming: { follows_convention: true, env: "prod", short_name: "lark", sequence: null, problems: [] },
  mce_default_mastertag: "4.16.27-x86_64",
  problems: [],
  segments_manager: null,
};
const CHARTS: DestinationCharts = {
  cluster: LARK, mce: MCE, id: `hosted:${SITE}:prod:${MCE}:${LARK}`, kind: "hosted", site: SITE, env: "prod", ocp_version: "4.16.27",
  installed: [], excluded: [], warnings: [], argocd_note: "",
};

function drift(overrides: Partial<ClusterDrift> = {}): ClusterDrift {
  return {
    cluster: LARK, site: SITE, mce: MCE, state: "in_sync", is_drifted: false,
    spec_name: FLAVOR, spec_version: "1.0.0", current_spec_version: "1.1.0",
    value_drift: [], addon_drift: [], version_differences: [], error: null, update: UPDATE_OPEN, ...overrides,
  };
}

const PREVIEW: SyncPreview = {
  cluster: LARK, site: SITE, mce: MCE, path: PATH, last_commit_id: READ_AT, spec_name: FLAVOR, spec_version: "1.1.0",
  file_spec_version: "1.0.0", changes: [],
  diff: `--- a/${PATH}\n+++ b/${PATH}\n@@ -1,2 +1,2 @@\n # specName: ${FLAVOR}\n-# specVersion: 1.0.0\n+# specVersion: 1.1.0`,
  removals: [], rebooting: [], problems: [], warnings: [], can_sync: true, addons_to_install: [], version_differences: [], addons_error: null,
};

/** The cluster page's reads, its drift from `answer` (read on each request), on the Drift tab. */
async function openCluster(page: Page, answer: () => ClusterDrift) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/clusters/bulk-status", (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
  await page.route(/\/api\/day1\/clusters\/[^/]+\/status\?/, (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "Live cluster status is disabled."));
  await page.route(`**/api/day1/clusters/${LARK}?**`, (r) => json(r, DETAIL));
  await page.route(`**/api/day1/clusters/${LARK}/drift?**`, (r) => json(r, answer()));
  await page.route(`**/api/day2/clusters/${LARK}/history?**`, (r) => json(r, []));
  await page.route(`**/api/day2/clusters/${LARK}/addons?**`, (r) => json(r, CHARTS));
  await page.route("**/api/day2/addons", (r) => json(r, []));
  await page.route(`**/api/day1/clusters/${LARK}/sync/preview?**`, (r) => json(r, PREVIEW));
  await go(page, `/clusters/${LARK}?site=${SITE}&mce=${MCE}`);
  await page.getByRole("tab", { name: "Drift" }).click();
}

test.describe("The cluster page and its update", () => {
  test("drift compares with the cluster's own version, and an open update MR is linked instead of Sync", async ({ page }) => {
    await openCluster(page, () => drift());

    await expect(page.getByText(`The cluster holds every value ${FLAVOR} v1.0.0 locks and has every add-on it lists.`)).toBeVisible();
    await expect(page.getByTestId("drift-compared-with")).toHaveText(`Compared with ${FLAVOR} v1.0.0, the version this cluster is on.`);
    const update = page.getByTestId("flavor-update");
    await expect(update).toHaveAttribute("data-state", "merge_request_open");
    await expect(update).toContainText(`${FLAVOR} v1.1.0 is out. Merge request !12 moves this cluster to it`);
    await expect(update.getByRole("link", { name: "Review the update MR !12" })).toHaveAttribute("href", "/approvals/day1-12");
    await expect(update.getByRole("link", { name: "Open !12 in GitLab" })).toHaveAttribute("href", MR12.web_url);
    await expect(page.getByRole("button", { name: "Sync to flavor" })).toHaveCount(0);
    // The header's badge says the same
    await expect(page.getByRole("main").getByTestId("flavor-state").first()).toHaveText("Update MR open (v1.0.0 → v1.1.0)");
  });

  test("a drifted cluster with an open update MR is linked to it, not offered a second sync", async ({ page }) => {
    await openCluster(page, () => drift({
      state: "drifted", is_drifted: true,
      value_drift: [{
        path: "owner_anaf", file_key: "owner.anaf", nodepool: null, flavor_value: "56", cluster_value: "57", in_file: true,
        added: [], removed: [], needs_decision: null, needs_hardware: false, reboots: false,
      }],
    }));

    await expect(page.getByText(`The cluster has drifted from ${FLAVOR} v1.0.0: 1 locked value differs.`)).toBeVisible();
    await expect(page.getByTestId("value-drift")).toBeVisible();
    await expect(page.getByTestId("flavor-update").getByRole("link", { name: "Review the update MR !12" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sync to flavor" })).toHaveCount(0);
  });

  test("a sync day1 refuses as already open (409) shows its detail, and the drift then links that MR", async ({ page }) => {
    let refused = false;
    await openCluster(page, () => drift({ update: refused ? UPDATE_OPEN : UPDATE }));
    const detail = `an open merge request already syncs ${LARK} to ${FLAVOR} v1.1.0: !12`;
    await page.route(`**/api/day1/clusters/${LARK}/sync?**`, (r) => {
      refused = true;
      return fulfillProblem(r, 409, "ALREADY_EXISTS", detail);
    });

    const update = page.getByTestId("flavor-update");
    await expect(update).toHaveAttribute("data-state", "available");
    await update.getByRole("button", { name: "Sync to flavor" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Open sync MR" }).click();

    const refusal = dialog.getByTestId("sync-refused");
    await expect(refusal).toContainText(`A merge request already syncs this cluster to ${FLAVOR} v1.1.0, so no second one was opened`);
    await expect(refusal).toContainText(detail);
    await dialog.getByRole("button", { name: "Back" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(update.getByRole("link", { name: "Review the update MR !12" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sync to flavor" })).toHaveCount(0);
  });
});

// ── The flavor's rollout ─────────────────────────────────────────────────────

const MR9 = mockMergeRequestLink(9, `[Wingman/Day1] Sync cluster ocp4-prod-kite-site1 to spec ${FLAVOR} v1.1.0`);
const MR13 = mockMergeRequestLink(13, `[Wingman/Day1] Sync cluster ocp4-prod-heron-site1 to spec ${FLAVOR} v1.1.0`);
const DECISION = "nodepool[1].configs: nodepool[1] has no network config (nm-conf-prod-owl-site1-<hardware>); choose its hardware type";

const FULL: RolloutStatus = mockRollout({
  spec_name: FLAVOR,
  version: "1.1.0",
  last_run: { trigger: "merge", started_at: "2026-11-12T10:15:00+00:00", finished_at: "2026-11-12T10:15:09+00:00", opened: 2, failed: 1 },
  clusters: [
    mockRolloutCluster("ocp4-prod-owl-site1", "needs_decision", { reasons: [DECISION] }),
    mockRolloutCluster("ocp4-prod-wren-site1", "failed", { reasons: ["GitLab did not answer the commit: timeout"] }),
    mockRolloutCluster("ocp4-prod-hawk-site1", "unknown", { from_version: null, reasons: ["the file is not valid YAML: line 3"] }),
    mockRolloutCluster("ocp4-prod-kite-site1", "declined", { merge_request: MR9 }),
    mockRolloutCluster("ocp4-prod-dove-site1", "pending"),
    mockRolloutCluster("ocp4-prod-heron-site1", "merge_request_open", { merge_request: MR13 }),
    mockRolloutCluster(LARK, "merge_request_open", { merge_request: MR12 }),
    mockRolloutCluster("ocp4-prod-swan-site1", "on_version", { from_version: "1.1.0" }),
  ],
});

/** The flavor page: its spec, its followers and its rollout (`rollout`: a body, or a handler read on each request). */
async function openFlavor(
  page: Page,
  { clusters = [] as SpecCluster[], rollout, asViewer = false }: { clusters?: SpecCluster[]; rollout?: RolloutStatus | ((route: Route) => Promise<void> | void); asViewer?: boolean } = {}
) {
  await injectAdminAuth(page);
  if (asViewer) await viewer(page);
  await mockDashboardApis(page);
  await page.route(/\/api\/day1\/specs\/agent-baseline(\?.*)?$/, (r) => json(r, SPEC));
  await page.route(`**/api/day1/specs/${FLAVOR}/clusters`, (r) => json(r, clusters));
  if (rollout) {
    await page.route(`**/api/day1/specs/${FLAVOR}/rollout`, (r) => (typeof rollout === "function" ? rollout(r) : json(r, rollout)));
  }
  await go(page, `/specs/${FLAVOR}`);
}

const clustersTab = (page: Page) => page.getByRole("button", { name: /^Clusters/ }).click();

test.describe("The flavor's rollout", () => {
  test("counts each state, lists the clusters that need a person first, with reasons and MR links", async ({ page }) => {
    await openFlavor(page, { rollout: FULL });

    // The overview says where it stands in a line
    await expect(page.getByTestId("flavor-rollout-summary")).toHaveText(
      "v1.1.0: 2 MRs open · 1 pending · 1 needs a decision · 1 declined · 1 failed · 1 unknown"
    );
    await clustersTab(page);
    const panel = page.getByTestId("rollout-panel");
    await expect(panel.getByRole("heading", { name: "Rollout of v1.1.0" })).toBeVisible();
    await expect(panel).toContainText("Each cluster that follows agent-baseline on an older version gets its own merge request to v1.1.0");
    await expect(panel.getByTestId("rollout-last-run")).toContainText("after the flavor's merge request merged: 2 merge requests opened, 1 failed.");
    for (const [state, n] of [["needs_decision", 1], ["failed", 1], ["unknown", 1], ["declined", 1], ["pending", 1], ["merge_request_open", 2], ["on_version", 1]] as const) {
      await expect(panel.getByTestId(`rollout-count-${state}`)).toContainText(String(n));
    }
    await expect(panel.getByTestId("rollout-counts")).toContainText("8 clusters");

    // Needs a decision and failed first
    const groups = panel.locator("[data-testid^=rollout-group-]");
    await expect(groups).toHaveCount(7);
    await expect(groups.nth(0)).toHaveAttribute("data-testid", "rollout-group-needs_decision");
    await expect(groups.nth(1)).toHaveAttribute("data-testid", "rollout-group-failed");
    await expect(groups.nth(6)).toHaveAttribute("data-testid", "rollout-group-on_version");

    const owl = panel.getByTestId("rollout-cluster-ocp4-prod-owl-site1");
    await expect(owl).toContainText(DECISION);
    await expect(owl).toContainText("on v1.0.0");
    await expect(owl.getByRole("link", { name: "Sync ocp4-prod-owl-site1 by hand" })).toHaveAttribute(
      "href", `/clusters/ocp4-prod-owl-site1?site=${SITE}&mce=${MCE}&tab=drift`
    );
    await expect(panel.getByTestId("rollout-group-needs_decision")).toContainText("No merge request opens for these until a person decides");
    await expect(panel.getByTestId("rollout-cluster-ocp4-prod-wren-site1")).toContainText("GitLab did not answer the commit: timeout");
    await expect(panel.getByTestId("rollout-group-failed")).toContainText("The next run tries again");
    await expect(panel.getByTestId("rollout-cluster-ocp4-prod-hawk-site1")).toContainText("the file is not valid YAML: line 3");

    const declined = panel.getByTestId("rollout-group-declined");
    await expect(declined).toContainText("Their customer closed the merge request without merging it, so no new one opens for v1.1.0");
    await expect(declined.getByRole("link", { name: "View !9 for ocp4-prod-kite-site1" })).toHaveAttribute("href", "/approvals/day1-9");
    await expect(declined.getByRole("link", { name: "Sync ocp4-prod-kite-site1 by hand" })).toBeVisible();

    const lark = panel.getByTestId(`rollout-cluster-${LARK}`);
    await expect(lark).toContainText(`!12 ${MR12.title}`);
    await expect(lark.getByRole("link", { name: `Review !12 for ${LARK}` })).toHaveAttribute("href", "/approvals/day1-12");
    await expect(lark.getByRole("link", { name: `Open !12 for ${LARK} in GitLab` })).toHaveAttribute("href", MR12.web_url);
    await expect(panel.getByTestId("rollout-group-pending")).toContainText("ocp4-prod-dove-site1");
    await expect(panel.getByTestId("rollout-group-on_version").getByRole("link", { name: "ocp4-prod-swan-site1" })).toBeVisible();
    await expect(panel.getByRole("button", { name: "Reconcile now" })).toBeEnabled();
  });

  test("is read again while day1 opens MRs, and no more once the run finished", async ({ page }) => {
    let reads = 0;
    await openFlavor(page, {
      rollout: (r) => {
        reads += 1;
        const running = reads < 3;
        return json(r, mockRollout({
          spec_name: FLAVOR, version: "1.1.0", running,
          clusters: [running ? mockRolloutCluster(LARK, "pending") : mockRolloutCluster(LARK, "merge_request_open", { merge_request: MR12 })],
        }));
      },
    });
    await clustersTab(page);

    const panel = page.getByTestId("rollout-panel");
    await expect(panel.getByTestId("rollout-running")).toContainText("Opening merge requests…");
    await expect(panel.getByRole("button", { name: "Reconcile now" })).toBeDisabled();
    await expect.poll(() => reads, { timeout: 15_000 }).toBeGreaterThanOrEqual(3);
    await expect(panel.getByTestId("rollout-running")).toHaveCount(0);
    await expect(panel.getByTestId(`rollout-cluster-${LARK}`)).toHaveAttribute("data-state", "merge_request_open");

    const settled = reads;
    await page.waitForTimeout(4_000);
    expect(reads).toBe(settled);
  });

  test("Reconcile now (admins) posts, shows the run, and follows it to its end", async ({ page }) => {
    const posts: Request[] = [];
    let reconciled = false;
    const before = mockRollout({
      spec_name: FLAVOR, version: "1.1.0",
      clusters: [mockRolloutCluster("ocp4-prod-wren-site1", "failed", { reasons: ["GitLab did not answer the commit: timeout"] })],
    });
    await openFlavor(page, {
      rollout: (r) => {
        if (r.request().method() === "POST") {
          posts.push(r.request());
          reconciled = true;
          return json(r, mockRollout({ ...before, running: true, clusters: [mockRolloutCluster("ocp4-prod-wren-site1", "pending")] }), 202);
        }
        return json(r, reconciled
          ? mockRollout({ ...before, clusters: [mockRolloutCluster("ocp4-prod-wren-site1", "merge_request_open", { merge_request: MR13 })] })
          : before);
      },
    });
    await clustersTab(page);

    const panel = page.getByTestId("rollout-panel");
    await expect(panel.getByTestId("rollout-cluster-ocp4-prod-wren-site1")).toHaveAttribute("data-state", "failed");
    await panel.getByRole("button", { name: "Reconcile now" }).click();
    await expect(panel.getByTestId("rollout-running")).toBeVisible();
    await expect(panel.getByTestId("rollout-cluster-ocp4-prod-wren-site1")).toHaveAttribute("data-state", "pending");
    expect(posts).toHaveLength(1);
    expect(new URL(posts[0].url()).pathname).toBe(`/api/day1/specs/${FLAVOR}/rollout`);

    await expect(panel.getByTestId("rollout-running")).toHaveCount(0, { timeout: 10_000 });
    await expect(panel.getByTestId("rollout-cluster-ocp4-prod-wren-site1")).toHaveAttribute("data-state", "merge_request_open");
  });

  test("a viewer sees the rollout but cannot reconcile", async ({ page }) => {
    await openFlavor(page, { rollout: FULL, asViewer: true });
    await clustersTab(page);

    await expect(page.getByTestId("rollout-panel").getByTestId("rollout-group-needs_decision")).toBeVisible();
    await expect(page.getByRole("button", { name: "Reconcile now" })).toHaveCount(0);
  });

  test("with no cluster following the flavor it says so, and offers nothing to reconcile", async ({ page }) => {
    await openFlavor(page, { rollout: mockRollout({ spec_name: FLAVOR, version: "1.1.0" }) });
    await clustersTab(page);

    await expect(page.getByTestId("rollout-empty")).toHaveText(
      "No cluster follows agent-baseline, so v1.1.0 has nowhere to roll out. A cluster created from it, or added to it, starts on its newest version."
    );
    await expect(page.getByRole("button", { name: "Reconcile now" })).toHaveCount(0);
    await expect(page.getByTestId("flavor-rollout-summary")).toHaveCount(0);
  });
});

// ── A flavor MR's approve page ───────────────────────────────────────────────

const SPECS_MR = mockMR({
  iid: 5, repo: "specs", project_id: 8, title: `[Wingman/Specs] Update spec ${FLAVOR}`,
  author: { username: "bob", name: "bob", avatar_url: "" }, sha: "5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a",
});
const SPEC_DIFF = {
  old_path: `specs/${FLAVOR}.yaml`, new_path: `specs/${FLAVOR}.yaml`,
  diff: "@@ -3,1 +3,1 @@\n-  version: 1.0.0\n+  version: 1.1.0\n", new_file: false, renamed_file: false, deleted_file: false,
};

const OPENS: ApprovalRollout = mockApprovalRollout({
  applies: true, reason: null, spec_name: FLAVOR, version: "1.1.0", current_version: "1.0.0",
  following: 16, opens: 12, already_on_version: 3,
  needs_decision: [{ name: "ocp4-prod-owl-site1", site: SITE, mce: MCE, reasons: [DECISION] }],
  rolls_nodes: [{
    name: LARK, site: SITE, mce: MCE,
    nodepools: [
      { name: "prod-lark-site1-dell-r660-site1", replicas: 3, replaces_nodes: false, max_unavailable: null },
      { name: "prod-lark-site1-cisco-c240-site1", replicas: 2, replaces_nodes: true, max_unavailable: null },
    ],
  }],
  removes_configs: [{ name: "ocp4-prod-heron-site1", site: SITE, mce: MCE, removals: [{ nodepool: "prod-heron-site1-dell-r660-site1", name: "restored-example-config" }] }],
  adds_addons: ["redbull/cluster-roles"],
});

/** The approve page of `mr`, its rollout answered by `rollout`; the rollout reads are kept. */
async function openApproval(page: Page, mr = SPECS_MR, rollout: ApprovalRollout = OPENS) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  let merged = false;
  const detail = (): ApprovalDetail => ({ mr: merged ? { ...mr, state: "merged" } : mr, diffs: [SPEC_DIFF] });
  await page.route(new RegExp(`/api/day1/approvals/${mr.iid}\\?repo=${mr.repo}$`), (r) => json(r, detail()));
  await page.route(new RegExp(`/api/day1/approvals/${mr.iid}/approve\\?repo=${mr.repo}$`), (r) => {
    merged = true;
    return json(r, { ...mr, state: "merged" });
  });
  const reads: string[] = [];
  await page.route(/\/api\/day1\/approvals\/\d+\/rollout(\?.*)?$/, (r) => {
    reads.push(r.request().url());
    return json(r, rollout);
  });
  await go(page, `/approvals/${mr.repo}-${mr.iid}`);
  await expect(page.getByRole("heading", { name: mr.title })).toBeVisible();
  return { reads };
}

test.describe("What merging a flavor MR opens", () => {
  test("the approve page counts the cluster MRs, the nodes that roll, the configs lost, the decisions and the add-ons", async ({ page }) => {
    const { reads } = await openApproval(page);

    const panel = page.getByTestId("approval-rollout");
    await expect(panel.getByTestId("approval-rollout-opens")).toHaveText("Merging opens 12 cluster merge requests");
    await expect(panel.getByTestId("approval-rollout-following")).toHaveText("· 16 clusters follow agent-baseline, 3 already on v1.1.0");
    await expect(panel).toContainText("This merge request moves agent-baseline from v1.0.0 to v1.1.0. Merging it is the one confirmation");
    await expect(panel).toContainText("which repeats what it does to that cluster");
    await expect(panel).toContainText("Nothing changes on a cluster until its own merge request merges.");
    expect(new URL(reads[0]).search).toBe("?repo=specs");

    const rolls = panel.getByTestId(`approval-rollout-rolls-${LARK}`);
    await expect(rolls).toContainText("prod-lark-site1-dell-r660-site1: Its 3 nodes are drained and rebooted in place, one node at a time.");
    await expect(rolls).toContainText("prod-lark-site1-cisco-c240-site1: Its 2 nodes are replaced with new nodes (upgradeType: Replace)");
    await expect(panel.getByTestId("approval-rollout-removes")).toContainText(
      "Removes restored-example-config from nodepool prod-heron-site1-dell-r660-site1"
    );
    const decisions = panel.getByTestId("approval-rollout-decisions");
    await expect(decisions).toContainText("No merge request opens for these");
    await expect(decisions.getByTestId("approval-rollout-decision-ocp4-prod-owl-site1")).toContainText(DECISION);
    await expect(panel.getByTestId("approval-rollout-addons")).toContainText("redbull/cluster-roles");

    // The approve dialog says it too, and once merged the page no longer shows what merging would open
    await page.getByRole("button", { name: /review & approve/i }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByTestId("approve-rollout-opens")).toContainText("Merging opens 12 cluster merge requests, one per cluster");
    await dialog.getByRole("button", { name: "Approve & Merge" }).click();
    await expect(page.getByText("!5 approved and merged")).toBeVisible();
    await expect(page.getByText("merged", { exact: true })).toBeVisible();
    await expect(page.getByTestId("approval-rollout")).toHaveCount(0);
  });

  test("an MR that gives no flavor a new version shows nothing of it", async ({ page }) => {
    const { reads } = await openApproval(page, { ...SPECS_MR, title: "[Wingman/Specs] Create spec agent-new" }, mockApprovalRollout());

    await expect.poll(() => reads.length).toBe(1);
    await expect(page.getByTestId("approval-rollout-loading")).toHaveCount(0);
    await expect(page.getByTestId("approval-rollout")).toHaveCount(0);
    await page.getByRole("button", { name: /review & approve/i }).click();
    await expect(page.getByRole("dialog").getByTestId("approve-rollout-opens")).toHaveCount(0);
  });

  test("a day1 MR does not ask", async ({ page }) => {
    const { reads } = await openApproval(page, mockMR({ iid: 42, author: { username: "alice", name: "alice", avatar_url: "" } }));

    await expect(page.getByText("Changed Files (1)")).toBeVisible();
    await page.waitForTimeout(1_000);
    expect(reads).toHaveLength(0);
    await expect(page.getByTestId("approval-rollout")).toHaveCount(0);
  });
});
