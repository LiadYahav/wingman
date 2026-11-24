/**
 * Customer MCEs (mocked; ADR-0067): each site's Customer MCEs, with no
 * default mastertag, each row opening its MCE's servers in Inventory
 * Management.
 */

import { test, expect, type Page } from "@playwright/test";
import { go, injectAdminAuth, json, mockDashboardApis } from "../fixtures/api-handlers";
import { MCES, SITE1_A } from "../fixtures/overview";

/** Sign in with day1's MCEs: site1's two Customer MCEs (a, b) and az1 seed, site2's one (a). */
async function openMces(page: Page) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/mces", (route) => json(route, MCES));
  await go(page, "/mces");
}

test.describe("Customer MCEs", () => {
  test("show each MCE's env, hub version and clusters, no default mastertag", async ({ page }) => {
    await openMces(page);

    const headers = page.getByTestId("mce-site").first().getByRole("columnheader");
    await expect(headers).toHaveText(["MCE", "Env", "Hub version", "Clusters", "Servers"]);
    await expect(page.getByText("Default mastertag")).toHaveCount(0);
  });

  test("each row opens its MCE's servers in Inventory Management", async ({ page }) => {
    await openMces(page);

    const row = page.locator(`[data-mce="${SITE1_A}"]`);
    const link = row.getByRole("link", { name: `${SITE1_A}: its servers in Inventory Management` });
    await expect(link).toHaveAttribute("href", `/inventory?mce=${SITE1_A}`);
    // Anywhere on the row: here by its clusters count, far from the name
    const box = (await row.boundingBox())!;
    await row.click({ position: { x: box.width - 80, y: box.height / 2 } });
    await expect(page).toHaveURL(new RegExp(`/inventory\\?mce=${SITE1_A}$`));
  });
});
