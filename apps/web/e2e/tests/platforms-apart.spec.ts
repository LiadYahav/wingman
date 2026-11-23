/**
 * The team keeps segments-manager and server-scan apart from Wingman (mocked;
 * ADR-0066). An admin's top bar has a
 * platform switch: Wingman, then Segments and Server Scan, each opening its
 * system's own UI in a new tab. Nothing in Wingman leads to a page of its own
 * for either. A viewer has no switch and never asks for the list.
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

const platform = (page: Page) => page.getByRole("navigation", { name: "Platform" });

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
  test("an admin's top bar links to each system's own UI in a new tab", async ({ page }) => {
    const { areaCalls } = await setUp(page);
    await go(page, "/");

    const links = platform(page).getByRole("link");
    await expect(links).toHaveText(["Wingman", /^Segments/, /^Server Scan/]);
    await expect(links.nth(0)).toHaveAttribute("aria-current", "page");
    await expect(links.nth(0)).toHaveAttribute("href", "/");
    for (const [name, url] of [["Segments", SEGMENTS_UI], ["Server Scan", SERVER_SCAN_UI]]) {
      const link = platform(page).getByRole("link", { name: new RegExp(`^${name}\\W*\\(opens in a new tab\\)$`) });
      await expect(link).toHaveAttribute("href", url);
      await expect(link).toHaveAttribute("target", "_blank");
      await expect(link).toHaveAttribute("rel", "noopener noreferrer");
      await expect(link).not.toHaveAttribute("aria-current", "page");
    }

    // Nothing in Wingman leads to a page of its own for either: not the switch, the sidebar or the Overview
    await expect(page.getByTestId("overview-servers")).toBeVisible();
    await expect(page.locator('a[href^="/server-scan"], a[href^="/segments"]')).toHaveCount(0);
    expect(areaCalls).toEqual([]);
  });

  test("a system day1 lists alone is the only link out", async ({ page }) => {
    await setUp(page, { platforms: [APART[1]] });
    await go(page, "/");
    await expect(platform(page).getByRole("link")).toHaveText(["Wingman", /^Server Scan/]);
  });

  test("with neither system configured there is no switch", async ({ page }) => {
    await setUp(page, { platforms: [] });
    await go(page, "/");
    await expect(page.getByTestId("overview-servers")).toBeVisible();
    await expect(platform(page)).toHaveCount(0);
  });

  test("a viewer has no switch, and never asks for the list", async ({ page }) => {
    const { reads, areaCalls } = await setUp(page, { viewer: true });
    await go(page, "/");
    await expect(page.getByTestId("overview-servers")).toBeVisible();
    await expect(platform(page)).toHaveCount(0);
    expect(reads()).toBe(0);
    expect(areaCalls).toEqual([]);
  });
});
