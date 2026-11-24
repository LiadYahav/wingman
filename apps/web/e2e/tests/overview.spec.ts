/**
 * The two Overviews (mocked; ADR-0067): the Customers one's header, its
 * numbers and versions, which count the tenants' clusters only; the
 * Infrastructure one's MCEs, seeds and capacity. Each card reads its own
 * source and loads, fails and empties on its own. The load, empty and failure
 * states of the stat row, Cluster Health and Pending Approvals are
 * page-states.spec.ts's.
 */

import { test, expect } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, injectViewerAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import { OVERVIEW as INVENTORY } from "../fixtures/inventory";
import { openOverview, RUNS, SITE1_A, SITE1_B, UPGRADES_OFF, WITH_KV } from "../fixtures/overview";

test.describe("The Overview's header", () => {
  test("offers an admin New Cluster, New Flavor and Browse Flavors, all one size", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await go(page, "/");

    const actions = page.getByTestId("overview-actions");
    const links = [
      actions.getByRole("link", { name: "New Cluster" }),
      actions.getByRole("link", { name: "New Flavor" }),
      actions.getByRole("link", { name: "Browse Flavors" }),
    ];
    await expect(links[0]).toHaveAttribute("href", "/clusters/new");
    await expect(links[1]).toHaveAttribute("href", "/specs/new");
    await expect(links[2]).toHaveAttribute("href", "/specs");
    const boxes = await Promise.all(links.map(async (link) => (await link.boundingBox())!));
    expect(new Set(boxes.map((box) => box.height)).size).toBe(1);
    // Beside the title, not below the cards
    const title = (await page.getByRole("heading", { name: "Overview", level: 1 }).boundingBox())!;
    expect(boxes[0].y).toBeLessThan(title.y + title.height);
  });

  test("offers a viewer only Browse Flavors", async ({ page }) => {
    await injectAdminAuth(page);
    await injectViewerAuth(page);
    await mockDashboardApis(page);
    await go(page, "/");

    const actions = page.getByTestId("overview-actions");
    await expect(actions.getByRole("link", { name: "Browse Flavors" })).toBeVisible();
    await expect(actions.getByRole("link", { name: "New Cluster" })).toHaveCount(0);
    await expect(actions.getByRole("link", { name: "New Flavor" })).toHaveCount(0);
  });
});

test.describe("The customers' clusters and their versions", () => {
  test("count each mastertag, newest first, and only the tenants' clusters", async ({ page }) => {
    await openOverview(page, { clusters: WITH_KV });

    // The KV cluster on the seed is the Infrastructure workspace's: five, not six
    await expect(page.getByTestId("stat-total-clusters")).toContainText("5");
    const versions = page.getByTestId("overview-version");
    await expect(versions).toHaveCount(4);
    expect(await versions.evaluateAll((rows) => rows.map((r) => r.getAttribute("data-version")))).toEqual([
      "4.18.40-x86_64", "4.18.22-x86_64", "4.17.9-x86_64", "",
    ]);
    await expect(versions.nth(1)).toHaveAccessibleName("4.18.22-x86_64: 2 clusters");
    await expect(versions.nth(3)).toHaveAccessibleName("Not set: 1 cluster");
    // Upgrades are off (mockDashboardApis): nothing is said of them
    await expect(page.getByTestId("overview-upgrades")).toHaveCount(0);
    // Where the clusters run and the free servers name the MCEs: not here
    await expect(page.getByTestId("overview-sites")).toHaveCount(0);
    await expect(page.getByTestId("overview-servers")).toHaveCount(0);
  });

  test("with upgrades on, count the clusters list's Upgrade filters and open them", async ({ page }) => {
    await openOverview(page, { upgrades: RUNS });

    // LARK's open run wins over its available release: one available, one upgrading
    const available = page.getByTestId("overview-upgrade-available");
    await expect(available).toHaveText("1 upgrade available");
    await expect(available).toHaveAttribute("href", "/clusters?upgrade=available");
    const upgrading = page.getByTestId("overview-upgrading");
    await expect(upgrading).toHaveText("1 upgrading");
    await upgrading.click();
    await expect(page).toHaveURL(/\/clusters\?upgrade=upgrading$/);
    await expect(page.getByTestId("cluster-row-ocp4-prod-lark-site1")).toBeVisible();
    await expect(page.getByTestId("cluster-row-ocp4-prod-owl-site1")).toHaveCount(0);
  });

  test("runs that cannot be read are unknown, never zero", async ({ page }) => {
    await openOverview(page, {
      upgrades: (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", "The workflows orchestrator did not answer"),
    });

    await expect(page.getByTestId("overview-upgrade-available")).toHaveText("2 upgrades available");
    await expect(page.getByTestId("overview-upgrading")).toHaveText("— upgrading");
  });

  test("with no clusters say so", async ({ page }) => {
    await openOverview(page, { clusters: [] });

    await expect(page.getByTestId("overview-versions-empty")).toContainText("No clusters yet");
  });
});

test.describe("Where the customers' clusters run (Infrastructure)", () => {
  test("count each site and its Customer MCEs, each opening Customer MCEs", async ({ page }) => {
    await openOverview(page, { clusters: WITH_KV, path: "/infrastructure" });

    const sites = page.getByTestId("overview-site");
    await expect(sites).toHaveCount(2);
    await expect(sites.nth(0)).toHaveAttribute("data-site", "site1");
    await expect(sites.nth(0)).toHaveAccessibleName("site1: 4 clusters");
    await expect(sites.nth(0).getByTestId("overview-site-mces")).toHaveText(`${SITE1_A}3${SITE1_B}1`);
    await expect(sites.nth(1)).toHaveAccessibleName("site2: 1 cluster");
    await expect(sites.nth(0)).toHaveAttribute("href", "/mces");
  });

  test("count the Customer MCEs, the seeds and the KV clusters", async ({ page }) => {
    await openOverview(page, { clusters: WITH_KV, path: "/infrastructure" });

    await expect(page.getByTestId("stat-customer-mces")).toContainText("3");
    await expect(page.getByTestId("stat-customer-mces")).toContainText("2 sites");
    await expect(page.getByTestId("stat-seeds")).toContainText("1 zone");
    await expect(page.getByTestId("stat-kv-clusters")).toContainText("1");
    await expect(page.getByTestId("stat-free-servers")).toContainText("Not set up here");
  });

  test("with no clusters say so", async ({ page }) => {
    await openOverview(page, { clusters: [], path: "/infrastructure" });

    await expect(page.getByTestId("overview-sites-empty")).toContainText("No clusters yet");
    await expect(page.getByTestId("overview-site")).toHaveCount(0);
  });
});

test.describe("Capacity (Infrastructure)", () => {
  test("free servers per MCE, each opening that MCE's servers in Inventory Management", async ({ page }) => {
    await openOverview(page, {
      clusters: UPGRADES_OFF,
      path: "/infrastructure",
      before: async (p) => {
        await p.route("**/api/day1/inventory", (route) => json(route, INVENTORY));
      },
    });

    const servers = page.getByTestId("overview-servers");
    await expect(servers.getByTestId("overview-servers-total")).toHaveText("10free across 2 MCEs");
    const mces = servers.getByTestId("overview-mce");
    await expect(mces).toHaveCount(2);
    await expect(mces.nth(0)).toHaveAccessibleName("ocp4-prod-mce-site1-a: 6 free of 16 servers");
    await expect(mces.nth(0)).toHaveAttribute("href", "/inventory?mce=ocp4-prod-mce-site1-a");
    // The most free pool first, the servers no single InfraEnv names last; one free server cannot be used now
    await expect(mces.nth(0).getByTestId("overview-pools")).toHaveText(
      "r650-mtl-az12hp-gen12-site1-64c-512gb0no single InfraEnv41 not usable"
    );
    await expect(servers.getByTestId("overview-servers-more")).toHaveText("1 MCE not in server-scan");
    await expect(page.getByTestId("stat-free-servers")).toContainText("10");
  });

  test("off here, Free Servers says so in one muted line", async ({ page }) => {
    await openOverview(page, { path: "/infrastructure" });

    await expect(page.getByTestId("overview-servers-off")).toContainText("Not set up here");
    await expect(page.getByTestId("overview-servers").getByRole("alert")).toHaveCount(0);
    await expect(page.getByTestId("overview-sites")).toBeVisible();
  });

  test("a failed read fails its own card only", async ({ page }) => {
    await openOverview(page, {
      path: "/infrastructure",
      before: async (p) => {
        await p.route("**/api/day1/inventory", (route) =>
          fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", "server-scan unreachable listing servers: ConnectError"));
      },
    });

    await expect(page.getByTestId("overview-servers").getByRole("alert")).toContainText("server-scan unreachable");
    await expect(page.getByTestId("overview-site")).toHaveCount(2);
  });

  test("a viewer reads neither: the Infrastructure Overview is an admin's", async ({ page }) => {
    let inventoryReads = 0;
    await openOverview(page, {
      viewer: true,
      path: "/infrastructure",
      before: async (p) => {
        await p.route("**/api/day1/inventory", (route) => {
          inventoryReads += 1;
          return json(route, INVENTORY);
        });
      },
    });

    await expect(page.getByTestId("admins-only")).toContainText("For admins");
    await expect(page.getByTestId("overview-mce")).toHaveCount(0);
    expect(inventoryReads).toBe(0);
  });
});
