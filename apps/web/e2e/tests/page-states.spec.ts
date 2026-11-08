/**
 * What the dashboard and the cluster list show while they load, when a list
 * is empty and when a read fails (mocked): skeletons shaped like the rows; an
 * empty list says what would be there and offers the next step; a failed read
 * is the service's RFC 9457 problem (detail and request id), never an empty list.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { fulfillProblem, injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";
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
    problems: [],
  };
}

/** Land on "/" first so the persisted session hydrates, then open the page. */
async function go(page: Page, path: string) {
  await page.goto("/");
  await page.waitForLoadState("domcontentloaded");
  if (path !== "/") {
    await page.goto(path);
    await page.waitForLoadState("domcontentloaded");
  }
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
    let answer: () => void = () => {};
    const answered = new Promise<void>((resolve) => (answer = resolve));
    await page.route("**/api/day1/clusters", async (r: Route) => {
      await answered;
      await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([cluster("ocp4-prod-alpha-site1")]) });
    });
    await page.goto("/clusters");

    await expect(page.locator("tbody [data-slot=skeleton]").first()).toBeVisible();
    await expect(page.getByTestId("clusters-empty")).toHaveCount(0);
    answer();
    await expect(page.getByTestId("cluster-row-ocp4-prod-alpha-site1")).toBeVisible();
    await expect(page.locator("tbody [data-slot=skeleton]")).toHaveCount(0);
  });

  test("filters that match nothing say so and clear in one click", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await page.route("**/api/day1/clusters", (r: Route) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([cluster("ocp4-prod-alpha-site1")]) })
    );
    await go(page, "/clusters");

    await page.getByPlaceholder("Search clusters...").fill("no-such-cluster");
    await expect(page.getByText("No clusters match")).toBeVisible();
    await page.getByRole("button", { name: "Clear filters" }).last().click();
    await expect(page.getByTestId("cluster-row-ocp4-prod-alpha-site1")).toBeVisible();
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
    await expect(alerts.filter({ hasText: "Failed to load clusters" })).toContainText("GitLab could not be reached", { timeout: 10_000 });
    await expect(page.getByTestId("clusters-empty")).toHaveCount(0);
  });
});
