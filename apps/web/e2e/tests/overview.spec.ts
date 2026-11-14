/**
 * The Overview's header and its sections (mocked): the next steps beside the
 * title, one size and one family; each card reads its own source and loads,
 * fails and empties on its own. The load, empty and failure states of the
 * stat row, Cluster Health and Pending Approvals are page-states.spec.ts's.
 */

import { test, expect } from "@playwright/test";
import { go, injectAdminAuth, injectViewerAuth, mockDashboardApis } from "../fixtures/api-handlers";

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
