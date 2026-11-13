/**
 * The sidebar collapses to an icon rail (mocked): by its button and by
 * Ctrl+B / ⌘B (never while typing), remembered in this browser and applied
 * before the page's scripts run, in Wingman and in every area's sidebar from
 * one choice. In the rail each entry is its icon, still a named link, with its
 * label (and a site's count) in a tooltip. Phones keep the slide-out sheet.
 */

import { test, expect, type Locator, type Page } from "@playwright/test";
import { go, mockAllApis } from "../fixtures/api-handlers";
import { setUpSegments } from "../fixtures/segments";

const RAIL = 56;
const FULL = 220;

const toggle = (page: Page) => page.getByTestId("sidebar-toggle");
const desktop = (page: Page) => page.locator("#app-sidebar");
const wingmanNav = (page: Page) => page.getByRole("navigation", { name: "Main" });
const segmentsNav = (page: Page) => page.getByRole("navigation", { name: "Segments" });
/** The open entry tooltip (the one just left may still be fading out). */
const tooltip = (page: Page) => page.locator("[data-testid=sidebar-tooltip][data-open]");
const brand = (page: Page) => page.getByTestId("brand");

const width = async (locator: Locator) => (await locator.boundingBox())?.width ?? -1;
const left = async (locator: Locator) => (await locator.boundingBox())?.x ?? -1;

/** Waits out the width transition. */
async function expectWidth(locator: Locator, expected: number) {
  await expect.poll(() => width(locator)).toBeCloseTo(expected, 0);
}

/** Clicks the toggle until the sidebar is `state`: a click before hydration does nothing, so it is retried. */
async function setSidebar(page: Page, state: "collapsed" | "expanded") {
  const expanded = state === "expanded" ? "true" : "false";
  await expect(async () => {
    if ((await toggle(page).getAttribute("aria-expanded")) !== expanded) await toggle(page).click();
    await expect(toggle(page)).toHaveAttribute("aria-expanded", expanded, { timeout: 1_000 });
  }).toPass();
}

/** Shown to screen readers only: the 1px box `sr-only` leaves. */
async function expectScreenReaderOnly(locator: Locator) {
  await expect.poll(() => width(locator)).toBeLessThanOrEqual(1);
}

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBe(0);
}

test.describe("The sidebar's icon rail", () => {
  test("starts expanded; its button collapses it to a rail and expands it, focus staying on the button", async ({ page }) => {
    await mockAllApis(page);
    await go(page, "/");
    const main = page.locator("main");
    await expect(toggle(page)).toHaveAttribute("aria-label", "Collapse sidebar");
    await expect(toggle(page)).toHaveAttribute("aria-expanded", "true");
    await expect(toggle(page)).toHaveAttribute("aria-controls", "app-sidebar");
    await expectWidth(desktop(page), FULL);
    const mainWidth = await width(main);

    await setSidebar(page, "collapsed");
    await expect(toggle(page)).toHaveAccessibleName("Expand sidebar");
    await expect(toggle(page)).toBeFocused();
    await expectWidth(desktop(page), RAIL);
    // The page takes the room: main starts where the rail ends and is wider by the difference
    await expect.poll(() => left(main)).toBeCloseTo(RAIL, 0);
    await expect.poll(() => width(main)).toBeCloseTo(mainWidth + FULL - RAIL, 0);
    await noHorizontalScroll(page);

    // Every entry stays a named link, its icon alone; the brand is its mark; headings are dividers
    const clusters = wingmanNav(page).getByRole("link", { name: "Clusters", exact: true });
    await expect(clusters).toBeVisible();
    expect(await width(clusters)).toBeLessThanOrEqual(RAIL - 16);
    await expect(brand(page).getByRole("img", { name: "Wingman" })).toBeVisible();
    expect(await width(brand(page))).toBeLessThanOrEqual(RAIL);
    await expectScreenReaderOnly(wingmanNav(page).getByText("Governance"));

    await toggle(page).click();
    await expect(toggle(page)).toHaveAccessibleName("Collapse sidebar");
    await expect(toggle(page)).toHaveAttribute("aria-expanded", "true");
    await expect(toggle(page)).toBeFocused();
    await expectWidth(desktop(page), FULL);
    await expect.poll(() => width(main)).toBeCloseTo(mainWidth, 0);
    await expect(wingmanNav(page).getByText("Governance")).toHaveText("Governance");
    expect(await width(wingmanNav(page).getByText("Governance"))).toBeGreaterThan(1);
  });

  test("Ctrl+B and ⌘B toggle it, but not while typing in a field", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments");
    await expect(page.getByTestId("segment-row")).toHaveCount(8);

    await page.keyboard.press("Control+b");
    await expect(toggle(page)).toHaveAttribute("aria-expanded", "false");
    await expectWidth(desktop(page), RAIL);
    await page.keyboard.press("Meta+b");
    await expect(toggle(page)).toHaveAttribute("aria-expanded", "true");
    await expectWidth(desktop(page), FULL);

    const search = page.getByRole("searchbox", { name: "Search segments" });
    await search.click();
    await page.keyboard.press("ControlOrMeta+b");
    await expect(search).toBeFocused();
    await expect(toggle(page)).toHaveAttribute("aria-expanded", "true");
    expect(await width(desktop(page))).toBeCloseTo(FULL, 0);
  });

  test("the choice survives a reload, at its width before the page's scripts run", async ({ page }) => {
    await mockAllApis(page);
    await go(page, "/");
    await setSidebar(page, "collapsed");
    expect(await page.evaluate(() => localStorage.getItem("wingman-sidebar"))).toBe("collapsed");

    // Hold every script: the first paint is the server's HTML, the inline script in <head> and the CSS
    let release: () => void = () => {};
    const released = new Promise<void>((resolve) => (release = resolve));
    const scripts = /\/_next\/static\/.*\.js(\?.*)?$/;
    await page.route(scripts, async (route) => {
      await released;
      await route.continue();
    });
    await page.reload({ waitUntil: "commit" });
    await expect(page.locator("html")).toHaveAttribute("data-sidebar-collapsed", "");
    await expectWidth(desktop(page), RAIL);
    // React has not run: the toggle still wears the server's label, yet the rail is already there
    await expect(toggle(page)).toHaveAttribute("aria-label", "Collapse sidebar");

    release();
    await expect(toggle(page)).toHaveAttribute("aria-label", "Expand sidebar");
    await expectWidth(desktop(page), RAIL);
    await page.unroute(scripts);

    await setSidebar(page, "expanded");
    await page.reload();
    await expect(toggle(page)).toHaveAttribute("aria-expanded", "true");
    await expect(page.locator("html")).not.toHaveAttribute("data-sidebar-collapsed");
    await expectWidth(desktop(page), FULL);
  });

  test("in the rail an icon navigates, its tooltip names it on hover and focus, and the active one is marked", async ({ page }) => {
    await mockAllApis(page);
    await go(page, "/");
    const nav = wingmanNav(page);
    const dashboard = nav.getByRole("link", { name: "Dashboard", exact: true });
    const clusters = nav.getByRole("link", { name: "Clusters", exact: true });

    // Expanded, the label is on the row: no tooltip
    await expect(nav.getByRole("link", { name: "Quick Links", exact: true })).toBeVisible();
    await clusters.hover();
    await page.waitForTimeout(300);
    await expect(page.getByTestId("sidebar-tooltip")).toHaveCount(0);

    await setSidebar(page, "collapsed");
    await expect(dashboard).toHaveAttribute("aria-current", "page");
    await clusters.hover();
    await expect(tooltip(page)).toHaveText("Clusters");
    await clusters.click();
    await expect(page).toHaveURL(/\/clusters$/);
    await expect(clusters).toHaveAttribute("aria-current", "page");
    await expect(dashboard).not.toHaveAttribute("aria-current", "page");
    await expect(toggle(page)).toHaveAttribute("aria-expanded", "false");

    // From the keyboard: the entry after the toggle is Dashboard, and focus shows its tooltip
    await page.mouse.move(600, 400);
    await toggle(page).focus();
    await page.keyboard.press("Tab");
    await expect(dashboard).toBeFocused();
    await expect(tooltip(page)).toHaveText("Dashboard");
  });

  test("Segments' sidebar follows the same choice: the brand is its mark, a site's count moves to its tooltip", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/");
    await setSidebar(page, "collapsed");

    await page.getByRole("navigation", { name: "Platform" }).getByRole("link", { name: "Segments" }).click();
    await expect(brand(page)).toHaveAttribute("data-area", "segments");
    await expect(toggle(page)).toHaveAttribute("aria-expanded", "false");
    await expectWidth(desktop(page), RAIL);
    await expect(brand(page)).toHaveAccessibleName("Segments Manager");
    expect(await width(brand(page))).toBeLessThanOrEqual(RAIL);
    await expectScreenReaderOnly(brand(page).getByText("Segments Manager"));

    const nav = segmentsNav(page);
    const site1 = nav.getByTestId("area-nav-site:site1");
    await expect(site1).toHaveAccessibleName(/^site1\s*4\/5\s*: 4 of 5 segments allocated$/);
    await expectScreenReaderOnly(site1.getByText("4/5"));
    await expectScreenReaderOnly(nav.getByText("Sites", { exact: true }));
    await site1.hover();
    await expect(tooltip(page)).toHaveText(/^site1\s*4\/5$/);

    await site1.click();
    await expect(page).toHaveURL(/site=site1/);
    await expect(site1).toHaveAttribute("aria-current", "page");
    await expect(page.getByTestId("segment-row")).toHaveCount(5);

    // Expanding here expands Wingman's too: one choice for every area
    await setSidebar(page, "expanded");
    await expect(site1.getByText("4/5")).toBeVisible();
    expect(await width(site1.getByText("4/5"))).toBeGreaterThan(1);
    await page.getByRole("navigation", { name: "Platform" }).getByRole("link", { name: "Wingman" }).click();
    await expect(brand(page)).toHaveAttribute("data-area", "wingman");
    await expect(toggle(page)).toHaveAttribute("aria-expanded", "true");
    await expectWidth(desktop(page), FULL);
  });
});

test.describe("On a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the slide-out sheet stays whole, with no rail and no toggle, even when the rail was chosen", async ({ page }) => {
    await mockAllApis(page);
    await page.addInitScript(() => localStorage.setItem("wingman-sidebar", "collapsed"));
    await go(page, "/");
    await expect(desktop(page)).toBeHidden();
    await expect(toggle(page)).toBeHidden();

    await page.getByRole("button", { name: "Open navigation" }).click();
    const sheet = page.getByRole("dialog");
    const clusters = sheet.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Clusters", exact: true });
    await expect(clusters).toBeVisible();
    expect(await width(clusters)).toBeGreaterThan(150);
    expect(await width(sheet.getByText("Governance"))).toBeGreaterThan(1);
    await expect(sheet.getByTestId("sidebar-toggle")).toHaveCount(0);
    await noHorizontalScroll(page);

    await clusters.click();
    await expect(page).toHaveURL(/\/clusters$/);
  });
});
