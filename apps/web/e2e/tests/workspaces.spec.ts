/**
 * The two workspaces (mocked; ADR-0067). An admin's top bar switches between
 * Customers, the tenants' side, and Infrastructure, what serves them, each
 * with its own sidebar; Help's pages keep the workspace you came from. A KV
 * cluster is Infrastructure's: listed under its seed, opened on the cluster
 * page there, managed as any cluster, and only its Delete asks for its name.
 * A viewer has no switch, and Infrastructure's pages say they are an admin's
 * without reading anything.
 */

import { test, expect, type Page, type Request, type Route } from "@playwright/test";
import { go, injectAdminAuth, injectViewerAuth, json, mockDashboardApis, mockMR } from "../fixtures/api-handlers";
import { KV_CLUSTER, MCES, SEED, WITH_KV } from "../fixtures/overview";
import { DETAIL, notDrifted } from "../fixtures/scale";
import type { ClusterDetail } from "@/types";

const KV = KV_CLUSTER.name;
const KV_DETAIL: ClusterDetail = {
  ...DETAIL,
  name: KV, mce: SEED, kind: "kv",
  path: `sites/site1/mces/${SEED}/hostedClusters/${KV}.yaml`,
  metadata: { ...DETAIL.metadata, mce: SEED },
  hosted_cluster: { cluster_name: "prod-kv-site1-az1-a", name: KV, namespace: "hcp-prod-kv-site1-az1-a" },
  naming: KV_CLUSTER.naming,
};

const workspaces = (page: Page) => page.getByRole("navigation", { name: "Workspace" });
const sidebar = (page: Page) => page.locator("[data-desktop-sidebar]").getByRole("navigation", { name: "Main" });

/** Sign in (as a viewer if asked) with the tenants' clusters, the az1 seed's KV cluster and day1's MCEs. */
async function setUp(page: Page, { viewer = false } = {}) {
  const reads: string[] = [];
  await injectAdminAuth(page);
  if (viewer) await injectViewerAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/clusters", (route) => json(route, WITH_KV));
  await page.route("**/api/day1/mces", (route) => {
    reads.push("mces");
    return json(route, MCES);
  });
  await page.route(`**/api/day1/clusters/${KV}?**`, (route) => json(route, KV_DETAIL));
  await page.route(`**/api/day1/clusters/${KV}/drift**`, (route) => json(route, { ...notDrifted, cluster: KV, mce: SEED }));
  return { reads };
}

async function entries(page: Page): Promise<string[]> {
  return sidebar(page).getByRole("link").allInnerTexts();
}

test.describe("An admin's two workspaces", () => {
  test("the top bar switches between Customers and Infrastructure, each with its own sidebar", async ({ page }) => {
    await setUp(page);
    await go(page, "/");

    const links = workspaces(page).getByRole("link");
    await expect(links).toHaveText(["Customers", "Infrastructure"]);
    await expect(links.nth(0)).toHaveAttribute("aria-current", "true");
    await expect(links.nth(1)).not.toHaveAttribute("aria-current", "true");
    expect(await entries(page)).toEqual(["Dashboard", "Clusters", "Flavors", "Addons", "Approvals", "Audit", "Lints", "Documentation", "Settings"]);

    await links.nth(1).click();
    await expect(page).toHaveURL(/\/infrastructure$/);
    await expect(links.nth(1)).toHaveAttribute("aria-current", "true");
    await expect(sidebar(page).getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
    expect(await entries(page)).toEqual([
      "Overview", "Customer MCEs", "Seeds & KV Clusters", "Inventory Management", "Quick Links", "Documentation", "Settings",
    ]);

    // Help's pages keep the workspace you came from
    await sidebar(page).getByRole("link", { name: "Documentation" }).click();
    await expect(page).toHaveURL(/\/docs$/);
    await expect(links.nth(1)).toHaveAttribute("aria-current", "true");
    await expect(sidebar(page).getByRole("link", { name: "Seeds & KV Clusters" })).toBeVisible();

    await links.nth(0).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(sidebar(page).getByRole("link", { name: "Clusters" })).toBeVisible();
  });

  test("Customer MCEs lists each site's MCEs, never a seed", async ({ page }) => {
    await setUp(page);
    await go(page, "/mces");

    const sites = page.getByTestId("mce-site");
    await expect(sites).toHaveCount(2);
    await expect(sites.nth(0).getByTestId("mce-row")).toHaveCount(2);
    await expect(page.locator(`[data-mce="${SEED}"]`)).toHaveCount(0);
    await expect(page.locator('[data-mce="ocp4-prod-mce-site1-a"]')).toContainText("4.18.22-x86_64");
  });

  test("Seeds & KV Clusters lists the seed and its KV cluster, which opens in Infrastructure", async ({ page }) => {
    await setUp(page);
    await go(page, "/seeds");

    const seed = page.getByTestId("seed");
    await expect(seed).toHaveAttribute("data-seed", SEED);
    await expect(seed).toContainText("az1");
    await seed.getByTestId("kv-cluster").click();

    await expect(page).toHaveURL(new RegExp(`/clusters/${KV}\\?`));
    await expect(page.getByTestId("kv-cluster-badge")).toHaveText("KV cluster · az1");
    await expect(workspaces(page).getByRole("link", { name: "Infrastructure" })).toHaveAttribute("aria-current", "true");
    await expect(sidebar(page).getByRole("link", { name: "Seeds & KV Clusters" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Back to Seeds & KV Clusters" })).toHaveAttribute("href", "/seeds");
    // Managed like any hosted cluster
    await expect(page.getByRole("button", { name: "Edit" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Nodes" })).toBeVisible();
  });

  test("the Clusters list is the customers': no KV cluster", async ({ page }) => {
    await setUp(page);
    await go(page, "/clusters");

    await expect(page.getByTestId("cluster-row-ocp4-prod-lark-site1")).toBeVisible();
    await expect(page.getByTestId(`cluster-row-${KV}`)).toHaveCount(0);
  });

  test("a KV cluster's Delete says its VMs go with it and needs its name, which day1 is sent", async ({ page }) => {
    await setUp(page);
    await go(page, `/clusters/${KV}?site=site1&mce=${SEED}`);
    const del = page.waitForRequest((req: Request) => req.method() === "DELETE");
    await page.route(`**/api/day1/clusters/${KV}?**`, async (r: Route) => {
      if (r.request().method() === "DELETE") return json(r, mockMR({ iid: 61 }));
      return json(r, KV_DETAIL);
    });

    await page.getByRole("button", { name: "Delete" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByTestId("kv-delete-confirm")).toContainText("The tenants' VMs go with it.");
    const confirm = dialog.getByRole("button", { name: /confirm/i });
    await expect(confirm).toBeDisabled();
    await dialog.getByLabel("The KV cluster's name, to confirm").fill("ocp4-prod-kv-site1-az1");
    await expect(confirm).toBeDisabled();
    await dialog.getByLabel("The KV cluster's name, to confirm").fill(KV);
    await confirm.click();

    const url = new URL((await del).url());
    expect(url.searchParams.get("confirm")).toBe(KV);
    expect(url.searchParams.get("last_commit_id")).toBe(KV_DETAIL.last_commit_id);
  });
});

test.describe("A viewer", () => {
  test("has no workspace switch and the Customers sidebar only", async ({ page }) => {
    await setUp(page, { viewer: true });
    await go(page, "/");

    await expect(page.getByTestId("overview-versions")).toBeVisible();
    await expect(workspaces(page)).toHaveCount(0);
    expect(await entries(page)).toEqual(["Dashboard", "Clusters", "Flavors", "Addons", "Approvals", "Audit", "Lints", "Documentation", "Settings"]);
  });

  for (const path of ["/infrastructure", "/mces", "/seeds", "/inventory"]) {
    test(`opening ${path} is told it is an admin's, and nothing is read`, async ({ page }) => {
      const { reads } = await setUp(page, { viewer: true });
      await go(page, path);

      await expect(page.getByTestId("admins-only")).toContainText("For admins");
      await expect(workspaces(page)).toHaveCount(0);
      await expect(sidebar(page).getByRole("link", { name: "Clusters" })).toBeVisible();
      expect(reads).toEqual([]);
    });
  }
});
