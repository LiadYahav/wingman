/**
 * Dev login on the rewritten day1 service (mocked): it needs the server's
 * DEV_AUTH_SECRET (401 without it, 404 when dev login is off), and a refused
 * login stays on the page with a clear message instead of bouncing to /login.
 */

import { test, expect, type Page, type Route, type Request } from "@playwright/test";
import { fulfillProblem, mockDashboardApis } from "../fixtures/api-handlers";

async function openLogin(page: Page, devAuthEnabled = true) {
  await page.route("**/api/auth/config", (r: Route) =>
    r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ authorize_url: "", dev_auth_enabled: devAuthEnabled }) })
  );
  await page.goto("/login");
  await page.waitForLoadState("domcontentloaded");
}

test.describe("Dev login", () => {
  test("sends the secret and lands on the dashboard", async ({ page }) => {
    await mockDashboardApis(page);
    await openLogin(page);
    const login = page.waitForRequest((req: Request) => req.url().endsWith("/api/auth/dev-login"));
    await page.route("**/api/auth/dev-login", (r: Route) =>
      r.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "fake-e2e-token",
          token_type: "bearer",
          user: { username: "alice", groups: ["wingman-dev-admins"], uid: "dev-alice", full_name: "Dev User (alice)", role: "admin" },
        }),
      })
    );

    await page.getByLabel("Username").fill("alice");
    await page.getByLabel("Dev login secret").fill("test-dev-secret-never-real-000001");
    await page.getByRole("combobox", { name: "Role" }).click();
    await page.getByRole("option", { name: "Admin" }).click();
    await page.getByRole("button", { name: "Sign in" }).click();

    expect((await login).postDataJSON()).toEqual({ username: "alice", role: "admin", secret: "test-dev-secret-never-real-000001" });
    await page.waitForURL((url) => url.pathname === "/");
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  });

  test("a wrong secret (401) stays on the page and says so", async ({ page }) => {
    await openLogin(page);
    await page.route("**/api/auth/dev-login", (r: Route) => fulfillProblem(r, 401, "UNAUTHORIZED", "the dev login secret is wrong"));

    await page.getByLabel("Username").fill("alice");
    await page.getByLabel("Dev login secret").fill("not-the-secret");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByText("The dev login secret is wrong.")).toBeVisible();
    await expect(page.getByLabel("Username")).toHaveValue("alice");
  });

  test("dev login switched off on the server (404) is explained", async ({ page }) => {
    await openLogin(page);
    await page.route("**/api/auth/dev-login", (r: Route) => fulfillProblem(r, 404, "NOT_FOUND", "dev login is not enabled"));

    await page.getByLabel("Username").fill("alice");
    await page.getByLabel("Dev login secret").fill("whatever");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByText("Dev login is turned off on this server.")).toBeVisible();
  });

  test("usernames follow the server's rule before anything is sent", async ({ page }) => {
    await openLogin(page);
    let sent = false;
    await page.route("**/api/auth/dev-login", (r: Route) => { sent = true; return r.abort(); });

    await page.getByLabel("Username").fill("Alice Smith");
    await expect(page.getByText(/Lowercase letters, digits/)).toBeVisible();
    await page.getByLabel("Dev login secret").fill("whatever");
    await page.getByRole("button", { name: "Sign in" }).click();
    expect(sent).toBe(false);
  });

  test("the secret is required", async ({ page }) => {
    await openLogin(page);
    await page.getByLabel("Username").fill("alice");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText(/dev login secret is required/)).toBeVisible();
  });

  test("without dev login there is no secret field", async ({ page }) => {
    await openLogin(page, false);
    await expect(page.getByRole("button", { name: "Log in via OpenShift" })).toBeVisible();
    await expect(page.getByLabel("Dev login secret")).toHaveCount(0);
  });
});
