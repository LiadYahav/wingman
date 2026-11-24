/**
 * The team keeps segments-manager and server-scan apart from Wingman (mocked;
 * ADR-0066, amended by ADR-0067). The Infrastructure workspace's sidebar
 * links to each system's own UI in a new tab, under Tools; the top bar is the
 * switch between the workspaces and links out to nothing. Nothing in Wingman
 * leads to a page of its own for either. A viewer has no such link and never
 * asks for the list.
 */

import { test, expect, type Page } from "@playwright/test";
import { go, injectAdminAuth, injectViewerAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import type { Platform } from "@/types";

const SEGMENTS_UI = "https://segments-manager.example";
const SERVER_SCAN_UI = "https://server-scan.example";
const APART: Platform[] = [
  { id: "segments", name: "Segments Manager", url: SEGMENTS_UI },
  { id: "server-scan", name: "Server Scan", url: SERVER_SCAN_UI },
];

const sidebar = (page: Page) => page.locator("[data-desktop-sidebar]").getByRole("navigation", { name: "Main" });

/**
 * Sign in (as a viewer if asked) with day1 listing `platforms`; returns how
 * often the list was read, and every call to a route of the removed areas.
 */
async function setUp(page: Page, { platforms = APART, viewer = false }: { platforms?: Platform[]; viewer?: boolean } = {}) {
  let reads = 0;
  const areaCalls: string[] = [];
  await injectAdminAuth(page);
  if (viewer) await injectViewerAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/mces", (route) => json(route, []));
  await page.route(/\/api\/day1\/(segments|server-scan)([/?].*)?$/, (route) => {
    areaCalls.push(route.request().url());
    return route.fulfill({ status: 404 });
  });
  await page.route("**/api/day1/platforms", (route) => {
    reads += 1;
    return json(route, { platforms });
  });
  return { reads: () => reads, areaCalls };
}

test.describe("The systems apart from Wingman", () => {
  test("Infrastructure's sidebar links to each system's own UI in a new tab", async ({ page }) => {
    const { areaCalls } = await setUp(page);
    await go(page, "/infrastructure");

    for (const [name, url] of [["Segments Manager", SEGMENTS_UI], ["Server Scan", SERVER_SCAN_UI]]) {
      const link = sidebar(page).getByRole("link", { name: new RegExp(`^${name}\\W*\\(opens in a new tab\\)$`) });
      await expect(link).toHaveAttribute("href", url);
      await expect(link).toHaveAttribute("target", "_blank");
      await expect(link).toHaveAttribute("rel", "noopener noreferrer");
      await expect(link).not.toHaveAttribute("aria-current", "page");
    }

    // The top bar switches workspaces only; nothing leads to a page of its own for either system
    await expect(page.getByRole("navigation", { name: "Workspace" }).locator("a[target=_blank]")).toHaveCount(0);
    await expect(page.locator('a[href^="/server-scan"], a[href^="/segments"]')).toHaveCount(0);
    expect(areaCalls).toEqual([]);
  });

  test("the Customers sidebar links out to neither", async ({ page }) => {
    await setUp(page);
    await go(page, "/");
    await expect(page.getByRole("navigation", { name: "Workspace" })).toBeVisible();
    await expect(sidebar(page).locator("a[target=_blank]")).toHaveCount(0);
  });

  test("a system day1 lists alone is the only link out", async ({ page }) => {
    await setUp(page, { platforms: [APART[1]] });
    await go(page, "/infrastructure");
    await expect(sidebar(page).locator("a[target=_blank]")).toHaveCount(1);
    await expect(sidebar(page).getByRole("link", { name: /^Server Scan/ })).toHaveAttribute("href", SERVER_SCAN_UI);
  });

  test("with neither system configured there is no link out", async ({ page }) => {
    await setUp(page, { platforms: [] });
    await go(page, "/infrastructure");
    await expect(sidebar(page).getByRole("link", { name: "Quick Links" })).toBeVisible();
    await expect(sidebar(page).locator("a[target=_blank]")).toHaveCount(0);
  });

  test("a viewer has no link out, and never asks for the list", async ({ page }) => {
    const { reads, areaCalls } = await setUp(page, { viewer: true });
    await go(page, "/");
    await expect(page.getByTestId("overview-versions")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Workspace" })).toHaveCount(0);
    await expect(sidebar(page).locator("a[target=_blank]")).toHaveCount(0);
    expect(reads()).toBe(0);
    expect(areaCalls).toEqual([]);
  });
});
