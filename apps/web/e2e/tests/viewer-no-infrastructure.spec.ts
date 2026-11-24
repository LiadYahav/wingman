/**
 * A viewer reads the tenants' clusters and never the infrastructure (ADR-0068,
 * mocked). day1 answers a viewer's cluster without its MCE, path or links; the
 * pages follow: no MCE, no file path, no EPG, no Segments Manager link, links
 * by name, and no request that names an MCE, even from an old link that does.
 * The Documentation leaves out the sections about the infrastructure, and the
 * query cache is one user's: signing out empties it.
 */

import { test, expect, type Page, type Request } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, injectViewerAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import type { ClusterDetail, ClusterLiveStatus, ClusterStatus } from "../../types";

const LARK = "ocp4-prod-lark-site1";
const MCE = "ocp4-prod-mce-site1-a";

/** lark as day1 lists it for a viewer: its site, no MCE, no path. */
const ROW: ClusterStatus = {
  name: LARK, site: "site1", mce: null, phase: "Unknown", spec_name: null, spec_version: null, created_by: "alice",
  created_at: "2026-11-07T10:00:00+00:00", mastertag: "4.18.22-x86_64", path: null,
  hosted_cluster: { cluster_name: "prod-lark-site1", name: "prod-lark-site1", namespace: "hcp-prod-lark-site1" },
  naming: { follows_convention: true, env: "prod", short_name: "lark", sequence: null, problems: [] },
  owner: { merkaz: "1" }, problems: [], upgrade_available: null,
};

/** lark's page as day1 answers a viewer: every field that names the MCE is null. */
const DETAIL: ClusterDetail = {
  name: LARK, site: "site1", mce: null, kind: "tenant",
  yaml: 'owner:\n  merkaz: "1"\nmastertag: 4.18.22-x86_64\nvlanId: 1412\n',
  gitlab_url: null, path: null, last_commit_id: "0c904bfafde4c4ed24416190ea224ee25cdcf738",
  metadata: {
    spec_name: null, spec_version: null, created_by: "alice", created_at: "2026-11-07T10:00:00+00:00",
    site: "site1", mce: null, variables: {}, immutable_paths: [], requested_addons: [],
  },
  values: {
    owner: { merkaz: "1" }, mastertag: "4.18.22-x86_64", platform: "agent",
    nodepools: [{ name: null, infra_env_name: "dell-r660-site1", replicas: 3, allow_deletion: false, configs: [], node_labels: {}, tuning_config: null }],
    network: { vlan_id: 1412, dhcp_network: "10.20.46.0", segment: "10.20.46.0/24" }, cluster_name: null, automation_keys: [],
  },
  hosted_cluster: ROW.hosted_cluster,
  naming: ROW.naming,
  mce_default_mastertag: null,
  problems: [],
  segments_manager: null,
};

const LIVE: ClusterLiveStatus = {
  cluster_name: LARK, hosted_cluster: "prod-lark-site1", namespace: "hcp-prod-lark-site1", hc_phase: "Ready",
  ocp_version: "4.18.22", hc_problems: [], node_pools: [], error: null,
};

/** Every API request from now on, by its URL, and the bulk-status bodies. */
function requests(page: Page): { urls: string[]; bulk: unknown[] } {
  const seen = { urls: [] as string[], bulk: [] as unknown[] };
  page.on("request", (request: Request) => {
    if (!request.url().includes("/api/")) return;
    seen.urls.push(request.url());
    if (request.url().endsWith("/bulk-status")) seen.bulk.push(request.postDataJSON());
  });
  return seen;
}

async function asViewer(page: Page) {
  await injectAdminAuth(page);
  await injectViewerAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/clusters", (r) => json(r, [ROW]));
  await page.route("**/api/day1/clusters/bulk-status", (r) => json(r, { [LARK]: LIVE }));
  await page.route(new RegExp(`/api/day1/clusters/${LARK}(\\?.*)?$`), (r) => json(r, DETAIL));
  await page.route(new RegExp(`/api/day1/clusters/${LARK}/drift(\\?.*)?$`), (r) =>
    json(r, {
      cluster: LARK, site: "site1", mce: null, state: "not_linked", is_drifted: false, spec_name: null, spec_version: null,
      current_spec_version: null, value_drift: [], addon_drift: [], version_differences: [], error: null,
    })
  );
  await page.route(new RegExp(`/api/day1/clusters/${LARK}/status(\\?.*)?$`), (r) => json(r, LIVE));
  await page.route(new RegExp(`/api/day1/clusters/${LARK}/status/stream`), (r) => fulfillProblem(r, 501, "FEATURE_DISABLED", "off"));
  await page.route(new RegExp(`/api/day2/clusters/${LARK}(/addons|/history)?(\\?.*)?$`), (r) =>
    fulfillProblem(r, 404, "NOT_FOUND", "no add-ons here")
  );
  await page.route("**/api/day2/addons", (r) => json(r, []));
}

test.describe("a viewer reads no infrastructure (ADR-0068)", () => {
  test("the clusters list shows the site, no MCE, links by name and asks status by name", async ({ page }) => {
    await asViewer(page);
    const seen = requests(page);
    await go(page, "/clusters");
    const row = page.getByRole("link", { name: LARK }).first();
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute("href", `/clusters/${LARK}`);
    await expect(page.getByText(MCE)).toHaveCount(0);
    await expect.poll(() => seen.bulk.length).toBeGreaterThan(0);
    expect(seen.bulk).toContainEqual({ clusters: [{ name: LARK }] });
    expect(seen.urls.filter((u) => u.includes("mce="))).toEqual([]);
  });

  test("a cluster's page names no MCE, path, EPG or Segments Manager, and sends no MCE", async ({ page }) => {
    await asViewer(page);
    const seen = requests(page);
    // An old link that carries the MCE: the page does not pass it on
    await go(page, `/clusters/${LARK}?site=site1&mce=${MCE}`);
    await expect(page.getByRole("heading", { name: LARK })).toBeVisible();
    await expect(page.getByText("site1").first()).toBeVisible();
    await expect(page.getByText(MCE)).toHaveCount(0);
    await expect(page.getByText("File", { exact: true })).toHaveCount(0);
    await expect(page.getByText("EPG", { exact: true })).toHaveCount(0);
    await expect(page.getByTestId("segments-manager")).toHaveCount(0);
    await expect(page.getByTestId("network-vlan")).toHaveText("1412");
    await expect(page.getByRole("link", { name: "GitLab" })).toHaveCount(0);
    await expect.poll(() => seen.urls.some((u) => new URL(u).pathname.endsWith(`/clusters/${LARK}/status`))).toBe(true);
    const named = seen.urls.filter((u) => new URL(u).search.includes("mce"));
    expect(named).toEqual([]);
    expect(seen.urls.filter((u) => new URL(u).pathname.endsWith("/network"))).toEqual([]);
  });

  test("the Documentation leaves out the infrastructure's sections and the MCE", async ({ page }) => {
    await asViewer(page);
    await go(page, "/docs");
    const contents = page.getByRole("navigation", { name: "Contents" });
    await expect(contents.getByRole("link", { name: "Clusters", exact: true })).toBeVisible();
    for (const admins of ["Workspaces", "Cluster Workflows", "Inventory Management", "Quick Links", "Special Features", "File Locations"]) {
      await expect(contents.getByRole("link", { name: admins, exact: true })).toHaveCount(0);
    }
    await expect(page.locator("#inventory")).toHaveCount(0);
    await expect(page.locator("section", { has: page.locator("#concepts") }).getByText("MCE", { exact: true })).toHaveCount(0);
  });
});

test("an admin's Documentation has every section", async ({ page }) => {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await go(page, "/docs");
  const contents = page.getByRole("navigation", { name: "Contents" });
  await expect(contents.getByRole("link", { name: "Inventory Management", exact: true })).toBeVisible();
  await expect(page.locator("section", { has: page.locator("#concepts") }).getByText("MCE", { exact: true })).toBeVisible();
});

test("signing out empties the stored reads: the cache is one user's", async ({ page }) => {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/clusters", (r) => json(r, [{ ...ROW, mce: MCE, path: `sites/site1/mces/${MCE}/hostedClusters/${LARK}.yaml` }]));
  await go(page, "/clusters");
  await expect(page.getByText(MCE).first()).toBeVisible();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("wingman-query-cache") ?? "")).toContain(MCE);
  await page.getByRole("button", { name: /test-admin/i }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL("**/login");
  expect(await page.evaluate(() => localStorage.getItem("wingman-query-cache"))).toBeNull();
});
