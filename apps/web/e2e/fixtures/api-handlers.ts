import { Page, Route } from "@playwright/test";
import { mockAddons, mockSpecs } from "./addons";

/**
 * Inject a fake authenticated admin user into localStorage/cookie so the app
 * doesn't redirect to /login.  Must be called before page.goto().
 *
 * IMPORTANT: After calling this, you must navigate to "/" first to establish
 * auth state, then navigate to your target page.  Direct navigation to a
 * sub-route may fail because Zustand's persist hydration is asynchronous.
 *
 * Usage:
 *   await injectAdminAuth(page);
 *   // ... register your route mocks ...
 *   await page.goto("/");           // establish auth
 *   await page.goto("/approvals");  // now navigate to target
 */
export async function injectAdminAuth(page: Page) {
  // Route the auth config check so it doesn't 401
  await page.route("**/api/auth/config", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ authorize_url: "/login", dev_auth_enabled: false }),
    });
  });

  // Pre-seed localStorage with a persisted auth state that Zustand will hydrate
  await page.addInitScript(() => {
    // Clear any stale query cache that could interfere with fresh test state
    localStorage.removeItem("wingman-query-cache");

    const authState = {
      state: {
        user: {
          username: "test-admin",
          groups: ["wingman-admins"],
          uid: "test-admin",
          full_name: "Test Admin",
          role: "admin",
        },
        isAuthenticated: true,
      },
      version: 0,
    };
    localStorage.setItem("wingman-auth", JSON.stringify(authState));

    // Set a fake token cookie so the API client includes it in requests
    document.cookie = "wingman-token=fake-e2e-token; path=/; SameSite=Strict";
  });
}

/**
 * Mock all dashboard APIs so that navigating to "/" doesn't cause 401s
 * that would redirect to login during auth establishment.
 */
export async function mockDashboardApis(page: Page) {
  await page.route("**/api/day1/clusters", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
  });
  await page.route("**/api/day1/clusters/drift-summary", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
  });
  await page.route("**/api/day1/approvals", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
  });
  await page.route("**/api/day2/approvals", async (route: Route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([]) });
  });
}

export async function mockDay2Api(page: Page) {
  await page.route("**/api/day2/addons", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockAddons),
    });
  });

  await page.route("**/api/day2/addons/*/**", async (route: Route) => {
    const url = route.request().url();
    const match = url.match(/\/api\/day2\/addons\/([^/]+)\/([^/]+)/);
    if (match) {
      const [, team, name] = match;
      const addon = mockAddons.find((a) => a.team === team && a.name === name);
      if (addon) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(addon),
        });
        return;
      }
    }
    await route.fulfill({ status: 404 });
  });
}

export async function mockDay1Api(page: Page) {
  await page.route("**/api/day1/specs", async (route: Route) => {
    const method = route.request().method();
    if (method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockSpecs),
      });
    } else if (method === "POST") {
      const body = route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ ...body, created: true }),
      });
    }
  });

  await page.route("**/api/day1/specs/*", async (route: Route) => {
    const method = route.request().method();
    const url = route.request().url();
    const name = url.split("/").pop();
    const spec = mockSpecs.find((s) => s.name === name);

    if (method === "GET" && spec) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(spec),
      });
    } else if (method === "PUT") {
      const body = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...body, updated: true }),
      });
    } else {
      await route.fulfill({ status: 404 });
    }
  });

  await page.route("**/api/day1/mces", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(["mce-east", "mce-west"]),
    });
  });

  await page.route("**/api/day1/sites", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(["site-a", "site-b", "site-c"]),
    });
  });
}

export async function mockAllApis(page: Page) {
  await injectAdminAuth(page);
  await mockDay1Api(page);
  await mockDay2Api(page);
}
