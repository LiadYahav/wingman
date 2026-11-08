/**
 * What the dashboard and the cluster list show while they load, when a list
 * is empty and when a read fails (mocked): skeletons shaped like the rows; an
 * empty list says what would be there and offers the next step; a failed read
 * is the service's RFC 9457 problem (detail and request id), never an empty list.
 */

import { test, expect, type Route } from "@playwright/test";
import { fulfillProblem, go, held, injectAdminAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import type { ClusterStatus } from "../../types";

function cluster(name: string): ClusterStatus {
  return {
    name,
    site: "site1",
    mce: "ocp4-prod-mce-site1-a",
    phase: "Unknown",
    spec_name: "agent-standard",
    spec_version: "1.0.0",
    created_by: "alice",
    created_at: "2026-11-07T10:00:00+00:00",
    mastertag: "4.16.27-x86_64",
    path: `sites/site1/mces/ocp4-prod-mce-site1-a/hostedClusters/${name}.yaml`,
    hosted_cluster: { cluster_name: name.replace(/^ocp4-/, ""), name: `openshift-${name.replace(/^ocp4-/, "")}`, namespace: `hcp-${name.replace(/^ocp4-/, "")}` },
    naming: { follows_convention: true, env: "prod", short_name: "x", sequence: null, problems: [] },
    owner: { merkaz: "1234", anaf: "56", mador: "7" },
    problems: [],
  };
}

test.describe("Clusters and the dashboard", () => {
  test("with no clusters both say so and offer to create one", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await go(page, "/");

    const health = page.getByTestId("health-empty");
    await expect(health).toContainText("No clusters yet");
    await expect(health.getByRole("link", { name: "New cluster" })).toHaveAttribute("href", "/clusters/new");
    await expect(page.getByTestId("approvals-empty")).toContainText("All caught up");

    await page.goto("/clusters");
    const empty = page.getByTestId("clusters-empty");
    await expect(empty).toContainText("No clusters yet");
    await expect(empty.getByRole("link", { name: "New cluster" })).toHaveAttribute("href", "/clusters/new");
  });

  test("while the list loads its rows are skeletons", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    const clusters = held();
    await page.route("**/api/day1/clusters", clusters.answer([cluster("ocp4-prod-alpha-site1")]));
    await go(page, "/clusters");

    await expect(page.locator("tbody [data-slot=skeleton]").first()).toBeVisible();
    await expect(page.getByTestId("clusters-empty")).toHaveCount(0);
    clusters.release();
    await expect(page.getByTestId("cluster-row-ocp4-prod-alpha-site1")).toBeVisible();
    await expect(page.locator("tbody [data-slot=skeleton]")).toHaveCount(0);
  });

  test("filters that match nothing say so and clear in one click", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await page.route("**/api/day1/clusters", (r: Route) => json(r, [cluster("ocp4-prod-alpha-site1")]));
    await go(page, "/clusters");

    await page.getByPlaceholder("Search clusters...").fill("no-such-cluster");
    await expect(page.getByText("No clusters match")).toBeVisible();
    await page.getByRole("button", { name: "Clear filters" }).last().click();
    await expect(page.getByTestId("cluster-row-ocp4-prod-alpha-site1")).toBeVisible();
  });

  test("approvals say all caught up only once both sources answered", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    const day2 = held();
    await page.route("**/api/day2/approvals", day2.answer([]));
    const day1Approvals = page.waitForResponse("**/api/day1/approvals");
    await go(page, "/");
    await day1Approvals;

    // The day1 reads answered and rendered; day2's is still out
    await expect(page.getByTestId("health-empty")).toBeVisible();
    await expect(page.getByTestId("approvals-empty")).toHaveCount(0);
    const pending = page.getByTestId("stat-pending-approvals");
    await expect(pending.locator("[data-slot=skeleton]")).toBeVisible();
    day2.release();
    await expect(page.getByTestId("approvals-empty")).toContainText("All caught up");
    await expect(pending).toContainText("0");
    await expect(pending.locator("[data-slot=skeleton]")).toHaveCount(0);
  });

  test("a failed read shows the problem, never an empty list", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await page.route("**/api/day1/clusters", (r: Route) => fulfillProblem(r, 503, "GIT_UNAVAILABLE", "GitLab could not be reached"));
    await page.route("**/api/day2/approvals", (r: Route) => fulfillProblem(r, 503, "GIT_UNAVAILABLE", "GitLab could not be reached"));
    await go(page, "/");

    // The default query retries twice (1s, 2s) before the error shows
    const alerts = page.getByRole("alert");
    await expect(alerts.filter({ hasText: "The clusters could not be loaded" })).toContainText("GitLab could not be reached", { timeout: 10_000 });
    await expect(alerts.filter({ hasText: "Day2 team MRs could not be loaded" })).toContainText("request req_e2e0000000000001");
    await expect(page.getByTestId("health-empty")).toHaveCount(0);
    await expect(page.getByTestId("approvals-empty")).toHaveCount(0);
    await expect(page.getByText("Could not be loaded", { exact: true })).toBeVisible();

    await page.goto("/clusters");
    await expect(alerts.filter({ hasText: "The clusters could not be loaded" })).toContainText("GitLab could not be reached", { timeout: 10_000 });
    await expect(page.getByTestId("clusters-empty")).toHaveCount(0);
  });

  test("a stat whose reads failed shows no value, never zero", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await page.route("**/api/day1/clusters", (r: Route) => json(r, [cluster("ocp4-prod-alpha-site1")]));
    await page.route("**/api/day1/clusters/bulk-status", (r: Route) => fulfillProblem(r, 503, "DEPENDENCY_UNAVAILABLE", "The MCE hub did not answer"));
    await page.route("**/api/day1/approvals", (r: Route) => fulfillProblem(r, 503, "GIT_UNAVAILABLE", "GitLab could not be reached"));
    await page.route("**/api/day2/approvals", (r: Route) => fulfillProblem(r, 503, "GIT_UNAVAILABLE", "GitLab could not be reached"));
    await go(page, "/");

    const ready = page.getByTestId("stat-ready");
    await expect(ready).toContainText("Could not be read");
    await expect(ready).toContainText("—");
    await expect(ready).not.toContainText("0");

    // The default query retries twice (1s, 2s) before the error shows
    const pending = page.getByTestId("stat-pending-approvals");
    await expect(pending).toContainText("Could not be loaded", { timeout: 10_000 });
    await expect(pending).toContainText("—");
    await expect(pending).not.toContainText("0");
  });
});
