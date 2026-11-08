/**
 * What the day2 pages show while they load, when a list is empty and when a
 * read or a write fails (mocked): skeletons shaped like what will be there; an
 * empty list says what would be there; a list its filters emptied offers to
 * clear them; a failed read is the service's RFC 9457 problem (detail and
 * request id), never an empty list or a missing section.
 */

import { test, expect, type Page, type Route } from "@playwright/test";
import { fulfillProblem, injectAdminAuth, mockDashboardApis } from "../fixtures/api-handlers";
import { HOSTED_NAME, day2Catalog, hostedCharts, mockDay2World } from "../fixtures/day2";

const REQUEST_ID = "request req_e2e0000000000001";
const UNREACHABLE = "GitLab could not be reached";

/** The legacy link from the day1 cluster page: a bare name and its MCE. */
const HOSTED_PAGE = `/clusters/${HOSTED_NAME}/addons?site=site1&mce=mce-a`;

/** The read of one chart on a destination (its values preview); writes fall through. */
const CERT_MANAGER = /\/api\/day2\/clusters\/[^/?]+\/addons\/platform\/cert-manager(\?.*)?$/;

const json = (route: Route, body: unknown) =>
  route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

const unreachable = (route: Route) => fulfillProblem(route, 503, "GIT_UNAVAILABLE", UNREACHABLE);

/** A route that answers only once `release()` is called. */
function held() {
  let release: () => void = () => {};
  const released = new Promise<void>((resolve) => (release = resolve));
  return { released, release };
}

/** Land on "/" first so the persisted session hydrates, then open the page. */
async function open(page: Page, path: string) {
  await page.goto("/");
  await page.waitForLoadState("domcontentloaded");
  await page.goto(path);
  await page.waitForLoadState("domcontentloaded");
}

test.beforeEach(async ({ page }) => {
  await injectAdminAuth(page);
  await mockDashboardApis(page);
  await mockDay2World(page);
});

test.describe("Lints", () => {
  test("a failed read shows the problem, never the all-clear", async ({ page }) => {
    await page.route("**/api/day2/lints**", unreachable);
    await open(page, "/lints");

    // The default query retries twice (1s, 2s) before the error shows
    const alert = page.getByRole("alert").filter({ hasText: "The lints could not be loaded" });
    await expect(alert).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(alert).toContainText(REQUEST_ID);
    await expect(page.getByTestId("lints-empty")).toHaveCount(0);
  });

  test("no findings is good news", async ({ page }) => {
    await page.route("**/api/day2/lints**", (r) => json(r, []));
    await open(page, "/lints");

    const empty = page.getByTestId("lints-empty");
    await expect(empty).toContainText("No findings");
    await expect(empty).toContainText("Every team repo passes every check.");
  });

  test("filters that match nothing say so and clear in one click", async ({ page }) => {
    await open(page, "/lints");
    const rows = page.locator("tbody tr");
    await expect(rows).toHaveCount(3);

    await page.getByPlaceholder("Search rules, messages, paths...").fill("no-such-rule");
    await expect(page.getByText("No findings match")).toBeVisible();
    await page.locator("tbody").getByRole("button", { name: "Clear filters" }).click();
    await expect(rows).toHaveCount(3);
    await expect(page.getByPlaceholder("Search rules, messages, paths...")).toHaveValue("");
  });
});

test.describe("Destinations", () => {
  test("a failed read shows the problem, never an empty list", async ({ page }) => {
    await page.route("**/api/day2/clusters", unreachable);
    await open(page, "/destinations");

    const alert = page.getByRole("alert").filter({ hasText: "The destinations could not be loaded" });
    await expect(alert).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(alert).toContainText(REQUEST_ID);
    await expect(page.getByTestId("destinations-empty")).toHaveCount(0);
  });

  test("with none it says where they come from and offers a new cluster", async ({ page }) => {
    await page.route("**/api/day2/clusters", (r) => json(r, []));
    await open(page, "/destinations");

    const empty = page.getByTestId("destinations-empty");
    await expect(empty).toContainText("No destinations yet");
    await expect(empty.getByRole("link", { name: "New cluster" })).toHaveAttribute("href", "/clusters/new");
  });

  test("filters that match nothing say so and clear in one click", async ({ page }) => {
    await open(page, "/destinations");
    const rows = page.locator("tbody tr");
    await expect(rows).toHaveCount(6);

    await page.getByRole("group", { name: "Kind" }).getByRole("button", { name: /UPI/ }).click();
    await page.getByPlaceholder("Search names, ids or teams...").fill("no-such-destination");
    await expect(page.getByText("No destinations match")).toBeVisible();
    await page.locator("tbody").getByRole("button", { name: "Clear filters" }).click();
    await expect(rows).toHaveCount(6);
  });
});

test.describe("Catalog", () => {
  test("while it loads the subtitle and the cards are skeletons", async ({ page }) => {
    const { released, release } = held();
    await page.route("**/api/day2/addons", async (r) => {
      await released;
      await json(r, day2Catalog);
    });
    await open(page, "/addons");

    await expect(page.locator("[data-slot=skeleton]").first()).toBeVisible();
    await expect(page.getByText(/Loading/)).toHaveCount(0);
    release();
    await expect(page.getByText("6 charts across 4 teams · 1 with warnings")).toBeVisible();
    await expect(page.locator("[data-slot=skeleton]")).toHaveCount(0);
  });

  test("a failed read shows the problem, never an empty catalog", async ({ page }) => {
    await page.route("**/api/day2/addons", unreachable);
    await open(page, "/addons");

    const alert = page.getByRole("alert").filter({ hasText: "The catalog could not be loaded" });
    await expect(alert).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(alert).toContainText(REQUEST_ID);
    await expect(page.getByTestId("catalog-empty")).toHaveCount(0);
    await expect(page.getByText(/0 charts/)).toHaveCount(0);
  });

  test("an empty catalog says how a chart gets there", async ({ page }) => {
    await page.route("**/api/day2/addons", (r) => json(r, []));
    await open(page, "/addons");

    await expect(page.getByTestId("catalog-empty")).toContainText("operators/<chart>/");
  });

  test("a search that matches nothing clears in one click", async ({ page }) => {
    await open(page, "/addons");
    await page.getByPlaceholder("Search addons or teams...").fill("no-such-chart");
    await expect(page.getByText("No charts match")).toBeVisible();
    await page.getByRole("button", { name: "Clear search" }).click();
    await expect(page.getByRole("button", { name: /prometheus/ })).toBeVisible();
  });
});

test.describe("A destination's charts", () => {
  test("while they load the section and its cards are skeletons", async ({ page }) => {
    const { released, release } = held();
    await page.route(/\/api\/day2\/clusters\/[^/?]+\/addons(\?.*)?$/, async (r) => {
      await released;
      await json(r, hostedCharts());
    });
    await open(page, HOSTED_PAGE);

    await expect(page.getByTestId("charts-loading")).toBeVisible();
    release();
    await expect(page.getByTestId("installed-platform-cert-manager")).toBeVisible();
    await expect(page.getByTestId("charts-loading")).toHaveCount(0);
  });

  test("a failed read shows the problem and the way back to the destinations", async ({ page }) => {
    await page.route(/\/api\/day2\/clusters\/[^/?]+\/addons(\?.*)?$/, unreachable);
    await open(page, HOSTED_PAGE);

    // A 5xx is retried once (1s) before the error shows
    const alert = page.getByRole("alert").filter({ hasText: `The charts of ${HOSTED_NAME} could not be loaded` });
    await expect(alert).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(alert).toContainText(REQUEST_ID);
    await expect(page.getByRole("link", { name: "Browse destinations" })).toHaveAttribute("href", "/destinations");
  });

  test("a failed catalog says so instead of hiding Available", async ({ page }) => {
    await page.route("**/api/day2/addons", unreachable);
    await open(page, HOSTED_PAGE);

    const availableSection = page.getByRole("region", { name: "Available" });
    await expect(availableSection.getByRole("alert")).toContainText("The catalog could not be loaded", { timeout: 10_000 });
    await expect(availableSection.getByRole("alert")).toContainText(REQUEST_ID);
    // What is installed is still shown
    await expect(page.getByTestId("installed-platform-cert-manager")).toBeVisible();
  });

  test("with every catalog chart installed, Available says so", async ({ page }) => {
    const installed = new Set(hostedCharts().installed.map((c) => `${c.team}/${c.name}`));
    await page.route("**/api/day2/addons", (r) => json(r, day2Catalog.filter((e) => installed.has(`${e.team}/${e.name}`))));
    await open(page, HOSTED_PAGE);

    await expect(page.getByRole("region", { name: "Available" }).getByTestId("available-empty")).toContainText(
      "Every catalog chart is installed here",
    );
    await expect(page.getByRole("button", { name: /Select all|Deselect all/ })).toHaveCount(0);
  });

  test("with no chart installed, the empty state points to Available", async ({ page }) => {
    await open(page, "/clusters/hub/addons");

    const empty = page.getByTestId("installed-empty");
    await expect(empty).toContainText("No team deploys a chart to hub yet");
    await expect(empty).toContainText("Install one from the Available charts below.");
  });

  test("while the values load, the Layers tab is a skeleton", async ({ page }) => {
    const { released, release } = held();
    await page.route(CERT_MANAGER, async (r) => {
      if (r.request().method() !== "GET") return r.fallback();
      await released;
      return r.fallback();
    });
    await open(page, HOSTED_PAGE);
    const card = page.getByTestId("installed-platform-cert-manager");
    await card.getByRole("button", { name: /^cert-manager/ }).click();
    await card.getByRole("tab", { name: "Layers" }).click();

    await expect(card.getByTestId("layers-loading")).toBeVisible();
    release();
    await expect(card.getByRole("list", { name: /Value layers/ })).toContainText("operators/cert-manager/values.yaml");
    await expect(card.getByTestId("layers-loading")).toHaveCount(0);
  });

  test("a failed values preview shows the problem", async ({ page }) => {
    await page.route(CERT_MANAGER, (r) => (r.request().method() === "GET" ? unreachable(r) : r.fallback()));
    await open(page, HOSTED_PAGE);
    const card = page.getByTestId("installed-platform-cert-manager");
    await card.getByRole("button", { name: /^cert-manager/ }).click();

    const alert = card.getByRole("alert").filter({ hasText: "The values could not be loaded" });
    await expect(alert).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(alert).toContainText(REQUEST_ID);
  });

  test("a failed upgrade check shows the problem", async ({ page }) => {
    const { released, release } = held();
    await page.route(/\/api\/day2\/clusters\/[^/?]+\/upgrade-check\?.*$/, async (r) => {
      await released;
      await unreachable(r);
    });
    await open(page, HOSTED_PAGE);
    await page.getByLabel("Upgrade check", { exact: true }).fill("4.19.3");
    await page.getByRole("button", { name: "Check", exact: true }).click();

    await expect(page.getByTestId("upgrade-check-loading")).toBeVisible();
    release();
    const alert = page.getByRole("alert").filter({ hasText: "The upgrade check to 4.19.3 could not be run" });
    await expect(alert).toContainText(UNREACHABLE, { timeout: 10_000 });
    await expect(alert).toContainText(REQUEST_ID);
    await expect(page.getByTestId("upgrade-check-loading")).toHaveCount(0);
  });

  test("a write GitLab did not confirm says it may have happened, with the request id", async ({ page }) => {
    await page.route(/\/api\/day2\/clusters\/[^/?]+\/addons\/observability\/grafana(\?.*)?$/, (r) =>
      r.request().method() === "POST"
        ? fulfillProblem(r, 502, "AMBIGUOUS_WRITE", "GitLab did not answer the commit request")
        : r.fallback(),
    );
    await open(page, HOSTED_PAGE);
    const card = page.getByTestId("available-observability-grafana");
    await card.getByRole("button", { name: "Install" }).click();
    await card.getByRole("button", { name: "Review install" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: /Create MR/ }).click();

    const alert = dialog.getByRole("alert");
    await expect(alert).toContainText("GitLab did not confirm the change, so it may or may not have been made");
    await expect(alert).toContainText("GitLab did not answer the commit request");
    await expect(alert).toContainText(REQUEST_ID);
  });
});
