/**
 * The settings page (mocked): the version and commit each service reports
 * (`GET /api/day{1,2}/build`), a warning when the two differ, and a theme
 * choice whose "System" follows the OS. The page renders without a
 * hydration mismatch: the theme is only known in the browser.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { fulfillProblem, go, injectAdminAuth, json, mockDashboardApis } from "../fixtures/api-handlers";

async function builds(page: Page, day1: (r: Route) => Promise<void>, day2: (r: Route) => Promise<void>) {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await page.route("**/api/day1/build", day1);
  await page.route("**/api/day2/build", day2);
}

/** Land on "/" first so the persisted session hydrates, then open settings. */
const open = (page: Page) => go(page, "/settings");

test.describe("Settings", () => {
  test("shows the version and commit each service runs", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    await builds(
      page,
      (r) => json(r, { version: "1.4.0", commit: "abc1234def5678" }),
      (r) => json(r, { version: "1.4.0", commit: "unknown" })
    );
    await open(page);

    await expect(page.getByTestId("build-day1")).toHaveText("1.4.0abc1234def5");
    await expect(page.getByTestId("build-day2")).toHaveText("1.4.0");
    await expect(page.getByTestId("build-skew")).toHaveCount(0);
    await expect(page.getByText("1.0.0")).toHaveCount(0);
    expect(errors.filter((e) => /hydrat/i.test(e))).toEqual([]);
  });

  test("warns when day1 and day2 run different versions", async ({ page }) => {
    await builds(
      page,
      (r) => json(r, { version: "1.4.0", commit: "abc1234" }),
      (r) => json(r, { version: "1.3.0", commit: "def5678" })
    );
    await open(page);

    await expect(page.getByTestId("build-day2")).toContainText("1.3.0");
    await expect(page.getByTestId("build-skew")).toContainText("day1 and day2 run different versions");
  });

  test("a build that cannot be read says so, not a version", async ({ page }) => {
    await builds(
      page,
      (r) => json(r, { version: "1.4.0", commit: "abc1234" }),
      (r) => fulfillProblem(r, 503, "DEPENDENCY_UNAVAILABLE", "day2 is not reachable")
    );
    await open(page);

    await expect(page.getByTestId("build-day1")).toContainText("1.4.0");
    // The query retries twice before it gives up.
    await expect(page.getByTestId("build-day2")).toHaveText("Could not be read", { timeout: 15_000 });
    await expect(page.getByTestId("build-skew")).toHaveCount(0);
  });

  test("System follows the OS's colour scheme", async ({ page }) => {
    await builds(
      page,
      (r) => json(r, { version: "1.4.0", commit: "abc1234" }),
      (r) => json(r, { version: "1.4.0", commit: "abc1234" })
    );
    await page.emulateMedia({ colorScheme: "light" });
    await open(page);

    const system = page.getByRole("button", { name: "System" });
    await system.click();
    await expect(system).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("html")).toHaveClass(/\blight\b/);

    await page.emulateMedia({ colorScheme: "dark" });
    await expect(page.locator("html")).toHaveClass(/\bdark\b/);

    await page.getByRole("button", { name: "Light" }).click();
    await expect(page.locator("html")).toHaveClass(/\blight\b/);
    await expect(system).toHaveAttribute("aria-pressed", "false");
  });
});
