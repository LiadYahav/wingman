import { Page, Route } from "@playwright/test";
import { mockAddons, mockSpecs } from "./addons";

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
  await mockDay1Api(page);
  await mockDay2Api(page);
}
