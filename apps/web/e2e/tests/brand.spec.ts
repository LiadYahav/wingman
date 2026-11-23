/**
 * Wingman's chrome (mocked): its logo and name at the top left, linking home,
 * and its sidebar, on every page. Five quick clicks on the brand show who
 * built Wingman.
 */

import { test, expect, type Page } from "@playwright/test";
import { go, injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";

const brand = (page: Page) => page.getByTestId("brand");
const wingmanNav = (page: Page) => page.getByRole("navigation", { name: "Main" });

test.describe("Wingman's chrome", () => {
  test.beforeEach(async ({ page }) => {
    await injectAdminAuth(page);
    await mockDashboardApis(page);
  });

  test("the brand is Wingman's logo, linking home, above Wingman's sidebar", async ({ page }) => {
    await go(page, "/clusters");
    await expect(brand(page)).toHaveAttribute("href", "/");
    await expect(brand(page).getByRole("img", { name: "Wingman" })).toBeVisible();
    for (const name of ["Dashboard", "Clusters", "Flavors", "Addons", "Quick Links", "Approvals", "Audit", "Lints", "Documentation", "Settings"]) {
      await expect(wingmanNav(page).getByRole("link", { name, exact: true })).toBeVisible();
    }
    await brand(page).click();
    await expect(page).toHaveURL(/\/$/);
  });

  test("five quick clicks on the brand show who built Wingman", async ({ page }) => {
    await go(page, "/");
    const credits = page.getByTestId("credits");

    for (let i = 0; i < 4; i += 1) await brand(page).click();
    await expect(credits).toHaveCount(0);
    await brand(page).click();
    await expect(credits).toContainText("Wingman");
    await expect(credits.getByTestId("credit")).toHaveText([/^Liad Yahav\s*2024 – 2026$/, /^& Roi Blum\s*2024 – 2028$/]);

    await credits.click();
    await expect(credits).toHaveCount(0);
  });
});
