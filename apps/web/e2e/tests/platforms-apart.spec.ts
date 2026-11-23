/**
 * The team keeps segments-manager and server-scan apart from Wingman (mocked;
 * ADR-0047 and ADR-0048's 2026-11-23 amendments). With both areas off, the
 * day1 default, an admin's top bar keeps its platform switch, whose Segments
 * and Server Scan entries open each system's own UI in a new tab; Wingman
 * offers neither `/segments` nor `/server-scan`, and a page opened by its
 * address says the area is off. An area turned on opens here, as before. A
 * viewer has no switch and never asks for the list.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, injectViewerAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import { mockSites } from "../fixtures/server-scan";
import type { Platform } from "@/types";

const SEGMENTS_UI = "https://segments-manager.example";
const SERVER_SCAN_UI = "https://server-scan.example";
const APART: Platform[] = [
  { id: "segments", name: "Segments Manager", url: SEGMENTS_UI, area: false },
  { id: "server-scan", name: "Server Scan", url: SERVER_SCAN_UI, area: false },
];

const platform = (page: Page) => page.getByRole("navigation", { name: "Platform" });
const brand = (page: Page) => page.getByTestId("brand");

/** day1's answer on an area's routes while the area is off: 501 naming its switch. */
const areaOff = (setting: string) => (route: Route) =>
  fulfillProblem(route, 501, "FEATURE_DISABLED", `The area is off in this deployment (${setting}=false).`, { setting });

/** Sign in (as a viewer if asked) with day1 listing `platforms`; returns how often the list was read. */
async function setUp(page: Page, { platforms = APART, viewer = false }: { platforms?: Platform[]; viewer?: boolean } = {}) {
  let reads = 0;
  await injectAdminAuth(page);
  if (viewer) await injectViewerAuth(page);
  await mockDashboardApis(page);
  // Every route of each area, its list (`/api/day1/segments`) too
  await page.route(/\/api\/day1\/segments([/?].*)?$/, areaOff("DAY1_SEGMENTS_AREA"));
  await page.route(/\/api\/day1\/server-scan([/?].*)?$/, areaOff("DAY1_SERVER_SCAN_AREA"));
  await page.route("**/api/day1/platforms", (route) => {
    reads += 1;
    return json(route, { platforms });
  });
  return { reads: () => reads };
}

test.describe("The systems apart from Wingman", () => {
  test("an admin's top bar links to each system's own UI in a new tab, and offers neither area", async ({ page }) => {
    await setUp(page);
    await go(page, "/");

    const links = platform(page).getByRole("link");
    await expect(links).toHaveText(["Wingman", /^Segments/, /^Server Scan/]);
    await expect(links.nth(0)).toHaveAttribute("aria-current", "page");
    for (const [name, url] of [["Segments", SEGMENTS_UI], ["Server Scan", SERVER_SCAN_UI]]) {
      const link = platform(page).getByRole("link", { name: new RegExp(`^${name}\\W*\\(opens in a new tab\\)$`) });
      await expect(link).toHaveAttribute("href", url);
      await expect(link).toHaveAttribute("target", "_blank");
      await expect(link).toHaveAttribute("rel", "noopener noreferrer");
      await expect(link).not.toHaveAttribute("aria-current", "page");
    }

    // Nothing in Wingman leads to the areas: not the switch, not the sidebar, not the Overview
    await expect(page.getByTestId("overview-servers")).toBeVisible();
    await expect(page.locator('a[href^="/server-scan"], a[href^="/segments"]')).toHaveCount(0);
    await expect(page.getByTestId("overview-segments")).toHaveCount(0);
    await expect(page.getByTestId("overview-health")).toHaveCount(0);
  });

  test("an area's page opened by its address says the area is off, in Wingman's chrome", async ({ page }) => {
    await setUp(page);
    await go(page, "/server-scan/servers");
    await expect(page.getByTestId("ss-area-off")).toContainText("Server Scan is in its own UI");
    await expect(brand(page)).toHaveAttribute("data-area", "wingman");
    await expect(platform(page).getByRole("link", { name: "Wingman" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("navigation", { name: "Server Scan" })).toHaveCount(0);

    await go(page, "/segments");
    await expect(page.getByTestId("segments-area-off")).toContainText("Segments is in its own UI");
    await expect(brand(page)).toHaveAttribute("data-area", "wingman");
  });

  test("an area turned on opens here, as before, beside the other one's link out", async ({ page }) => {
    await setUp(page, { platforms: [APART[0], { ...APART[1], area: true }] });
    await page.route("**/api/day1/server-scan/sites", (route) => json(route, mockSites()));
    await go(page, "/");

    await expect(platform(page).getByRole("link")).toHaveText(["Wingman", /^Segments/, "Server Scan"]);
    await expect(platform(page).getByRole("link", { name: "Server Scan" })).toHaveAttribute("href", "/server-scan");
    await expect(platform(page).getByRole("link", { name: "Server Scan" })).not.toHaveAttribute("target", "_blank");
    await expect(platform(page).getByRole("link", { name: /^Segments/ })).toHaveAttribute("href", SEGMENTS_UI);
  });

  test("a viewer has no switch, and never asks for the list", async ({ page }) => {
    const { reads } = await setUp(page, { viewer: true });
    await go(page, "/");
    await expect(page.getByTestId("overview-servers")).toBeVisible();
    await expect(platform(page)).toHaveCount(0);
    expect(reads()).toBe(0);
  });
});
