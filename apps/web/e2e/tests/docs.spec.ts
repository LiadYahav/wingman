/**
 * The in-app Documentation page (mocked): every Contents entry and every
 * link inside the page opens a section of it, so a section renamed or left
 * out of the page cannot leave a dead entry.
 */

import { test, expect, type Page } from "@playwright/test";
import { go, injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";

const contentsNav = (page: Page) => page.getByRole("navigation", { name: "Contents" });

test.describe("The Documentation page", () => {
  test("every Contents entry and in-page link opens a section of the page", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await go(page, "/docs");
    await expect(page.getByRole("heading", { name: "Wingman Platform", level: 1 })).toBeVisible();
    // An admin's sections appear once the role is known (ADR-0068: a viewer's leave them out)
    await expect(contentsNav(page).getByRole("link", { name: "Inventory Management" })).toBeVisible();

    const contents = await contentsNav(page).getByRole("link").evaluateAll((links) => links.map((a) => a.getAttribute("href") ?? ""));
    expect(contents).toEqual(expect.arrayContaining(["#home", "#cluster-workflows", "#inventory", "#quick-links"]));
    // segments-manager and server-scan live in their own UIs: the docs have no section of their own for them
    expect(contents).not.toContain("#segments");
    expect(contents).not.toContain("#server-scan");
    const anchors = await page.locator('a[href^="#"]').evaluateAll((links) => links.map((a) => a.getAttribute("href") ?? ""));
    for (const href of new Set([...contents, ...anchors])) {
      await expect(page.locator(href), `${href} is a section of the page`).toHaveCount(1);
    }
  });

  test("a Contents entry brings its section into view", async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
    await go(page, "/docs");

    await contentsNav(page).getByRole("link", { name: "Quick Links" }).click();
    await expect(page).toHaveURL(/#quick-links$/);
    await expect(page.getByRole("heading", { name: "Quick Links", level: 2 })).toBeInViewport();
  });
});
