/**
 * Each area wears its own chrome (mocked; ADR-0047's amendment): the brand at
 * the top left and the sidebar. In Segments, segments-manager's rack mark and
 * name, and a sidebar of the page's own options (status presets, every site
 * with used out of total, Documentation), each a link that sets the URL
 * filters and is marked from the URL. Wingman's pages keep Wingman's logo and
 * sidebar; a viewer never sees the Segments chrome. Five quick clicks on an
 * area's brand show who built it.
 */

import { test, expect, type Page } from "@playwright/test";
import { go } from "../fixtures/api-handlers";
import { forbidden, setUpSegments } from "../fixtures/segments";
import { setUpServerScan } from "../fixtures/server-scan";

const brand = (page: Page) => page.getByTestId("brand");
const segmentsNav = (page: Page) => page.getByRole("navigation", { name: "Segments" });
const wingmanNav = (page: Page) => page.getByRole("navigation", { name: "Main" });
const platform = (page: Page) => page.getByRole("navigation", { name: "Platform" });
const rows = (page: Page) => page.getByTestId("segment-row");

test.describe("Each area's chrome", () => {
  test("Segments has its own brand and sidebar, and the brand opens the area's home", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments?status=allocated");

    await expect(brand(page)).toHaveAttribute("data-area", "segments");
    await expect(brand(page)).toHaveText("Segments Manager");
    await expect(brand(page)).toHaveAttribute("href", "/segments");
    await expect(wingmanNav(page)).toHaveCount(0);
    await expect(platform(page).getByRole("link", { name: "Segments" })).toHaveAttribute("aria-current", "page");

    const nav = segmentsNav(page);
    await expect(nav.getByTestId("area-nav-section").locator("p").first()).toHaveText("Segments");
    await expect(nav.getByRole("link")).toHaveText([
      "All", "Available", "Allocated", "Disagrees with Git",
      /^site1\s*4\/5/, /^site2\s*1\/3/, /^site3\s*0\/0/,
      "Documentation",
    ]);
    await expect(nav.getByRole("link", { name: "Documentation" })).toHaveAttribute("href", "/docs#segments");

    await brand(page).click();
    await expect(page).toHaveURL(/\/segments$/);
    await expect(rows(page)).toHaveCount(8);
  });

  test("the sidebar's entries set the page's filters and are marked from the URL", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments");
    const nav = segmentsNav(page);
    await expect(nav.getByTestId("area-nav-all")).toHaveAttribute("aria-current", "page");

    await nav.getByTestId("area-nav-allocated").click();
    await expect(page).toHaveURL(/status=allocated/);
    await expect(rows(page)).toHaveCount(5);
    await expect(nav.getByTestId("area-nav-allocated")).toHaveAttribute("aria-current", "page");
    await expect(nav.getByTestId("area-nav-all")).not.toHaveAttribute("aria-current", "page");

    // A site keeps the status; the page's own filters agree with the sidebar
    await nav.getByTestId("area-nav-site:site2").click();
    await expect(page).toHaveURL(/status=allocated&site=site2/);
    await expect(rows(page)).toHaveCount(1);
    await expect(nav.getByTestId("area-nav-site:site2")).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("group", { name: "Site" }).getByRole("button", { name: "site2" })).toHaveAttribute("aria-pressed", "true");

    // The page's own controls move the sidebar's mark too
    await page.getByRole("group", { name: "Status" }).getByRole("button", { name: /^All \d/ }).click();
    await expect(nav.getByTestId("area-nav-all")).toHaveAttribute("aria-current", "page");

    await nav.getByTestId("area-nav-mismatch").click();
    await expect(page).toHaveURL(/mismatch=1/);
    await expect(nav.getByTestId("area-nav-mismatch")).toHaveAttribute("aria-current", "page");
    await expect(rows(page)).toHaveCount(0);
  });

  test("Wingman's pages keep Wingman's logo and sidebar", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/");
    await expect(brand(page)).toHaveAttribute("data-area", "wingman");
    await expect(brand(page)).toHaveAttribute("href", "/");
    await expect(brand(page).getByRole("img", { name: "Wingman" })).toBeVisible();
    await expect(segmentsNav(page)).toHaveCount(0);
    for (const name of ["Dashboard", "Clusters", "Flavors", "Addons", "Quick Links", "Approvals", "Audit", "Lints", "Documentation", "Settings"]) {
      await expect(wingmanNav(page).getByRole("link", { name, exact: true })).toBeVisible();
    }
    await expect(platform(page).getByRole("link", { name: "Wingman" })).toHaveAttribute("aria-current", "page");

    // Switching platform switches the chrome, and back
    await platform(page).getByRole("link", { name: "Segments" }).click();
    await expect(brand(page)).toHaveText("Segments Manager");
    await platform(page).getByRole("link", { name: "Wingman" }).click();
    await expect(brand(page)).toHaveAttribute("data-area", "wingman");
    await expect(wingmanNav(page)).toBeVisible();
  });

  test("a viewer never sees the Segments chrome", async ({ page }) => {
    await setUpSegments(page, { viewer: true, list: forbidden, stats: forbidden, sites: forbidden });
    await go(page, "/");
    await page.goto("/segments");
    await expect(page.getByTestId("segments-forbidden")).toBeVisible();
    await expect(brand(page)).toHaveAttribute("data-area", "wingman");
    await expect(wingmanNav(page)).toBeVisible();
    await expect(segmentsNav(page)).toHaveCount(0);
    await expect(platform(page)).toHaveCount(0);
  });

  for (const { area, path, setUp, credits: expected } of [
    { area: "wingman", path: "/", setUp: setUpSegments, credits: [/^Liad Yahav\s*2024 – 2026$/, /^& Roi Blum\s*2024 – 2028$/] },
    { area: "segments", path: "/segments", setUp: setUpSegments, credits: [/^Roi Blum\s*2024 – 2028$/, /^& Itay Herzberg\s*2026 – 2028$/] },
    { area: "server-scan", path: "/server-scan", setUp: setUpServerScan, credits: [/^Roi Blum\s*2024 – 2028$/, /^& Tomer Karniol\s*2025 – 2042$/] },
  ] as const) {
    test(`five quick clicks on ${area}'s brand show who built it`, async ({ page }) => {
      await setUp(page);
      await go(page, path);
      await expect(brand(page)).toHaveAttribute("data-area", area);
      const credits = page.getByTestId("credits");

      for (let i = 0; i < 4; i += 1) await brand(page).click();
      await expect(credits).toHaveCount(0);
      await brand(page).click();
      await expect(credits).toHaveAttribute("data-area", area);
      await expect(credits.getByTestId("credit")).toHaveText([...expected]);

      await credits.click();
      await expect(credits).toHaveCount(0);
    });
  }
});
