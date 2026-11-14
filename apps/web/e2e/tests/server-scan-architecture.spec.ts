/**
 * The Server Scan area's Architecture page (mocked; docs/notes/2026-11-13-server-scan-area-api.md
 * §11, ADR-0048's 3.28.0 amendment): server-scan's diagrams as its UI serves
 * them, read through day1 and shown in a sandboxed frame; server-scan's
 * picker, words and descriptions, the diagram in the URL, Wingman's theme
 * passed in, and the states.
 */

import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, go, held, json } from "../fixtures/api-handlers";
import { diagramPage, setUpArchitecture } from "../fixtures/server-scan-architecture";

const PAGE = "/server-scan/architecture";
const frame = (page: Page) => page.frameLocator('[data-testid="ss-diagram-frame"]');
const tab = (page: Page, name: string) => page.getByRole("tab", { name, exact: true });

test.describe("The Architecture page", () => {
  test("the sidebar opens it on the full flow, server-scan's picker and words above the diagram", async ({ page }) => {
    const { asked } = await setUpArchitecture(page);
    await go(page, "/server-scan");
    const nav = page.getByRole("navigation", { name: "Server Scan" });
    await expect(nav.getByRole("link")).toHaveText(["Sites", "Servers", "Confs", "Rules & Policies", "Claude", "Architecture"]);
    await nav.getByRole("link", { name: "Architecture" }).click();
    await expect(page).toHaveURL(/\/server-scan\/architecture$/);
    await expect(page.getByRole("heading", { level: 1, name: "Architecture" })).toBeVisible();
    await expect(nav.getByTestId("area-nav-architecture")).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("tablist", { name: "Diagram" }).getByRole("tab")).toHaveText([
      "Full flow",
      "Cisco UCS Central",
      "Cisco Intersight",
      "Dell OpenManage",
      "HPE OneView",
      "Redfish Standalone",
      "Nodes Status",
    ]);
    await expect(tab(page, "Full flow")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("ss-diagram-description")).toHaveText(/^Every collector through Mongo/);
    await expect(page.getByTitle("Full flow architecture diagram")).toBeVisible();
    await expect(frame(page).getByRole("heading")).toHaveText("Diagram runtime-architecture");
    expect(asked).toEqual(["runtime-architecture"]);
  });

  test("the diagram's scripts run in a sandbox: they reach nothing of Wingman's", async ({ page }) => {
    await setUpArchitecture(page);
    await go(page, PAGE);
    const element = page.getByTestId("ss-diagram-frame");
    await expect(element).toHaveAttribute("sandbox", "allow-scripts allow-downloads");
    await expect(frame(page).locator("#reach")).toHaveText("kept out, no storage");
  });

  test("picking a diagram shows it and puts it in the URL; each is read once", async ({ page }) => {
    const { asked } = await setUpArchitecture(page);
    await go(page, PAGE);
    await expect(frame(page).getByRole("heading")).toHaveText("Diagram runtime-architecture");
    await tab(page, "Cisco UCS Central").click();
    await expect(page).toHaveURL(/\/server-scan\/architecture\?diagram=ucs-central$/);
    await expect(tab(page, "Cisco UCS Central")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("ss-diagram-description")).toHaveText(/^Central login, per-domain UCS Manager sessions/);
    await expect(frame(page).getByRole("heading")).toHaveText("Diagram ucs-central");
    await tab(page, "Full flow").click();
    await expect(page).toHaveURL(/\/server-scan\/architecture$/);
    await expect(frame(page).getByRole("heading")).toHaveText("Diagram runtime-architecture");
    expect(asked).toEqual(["runtime-architecture", "ucs-central"]);
  });

  test("the diagram named in the URL opens; a name server-scan's list lacks opens the first", async ({ page }) => {
    await setUpArchitecture(page);
    await go(page, `${PAGE}?diagram=oneview`);
    await expect(tab(page, "HPE OneView")).toHaveAttribute("aria-selected", "true");
    await expect(frame(page).getByRole("heading")).toHaveText("Diagram oneview");
    await page.goto(`${PAGE}?diagram=gone`);
    await expect(tab(page, "Full flow")).toHaveAttribute("aria-selected", "true");
    await expect(frame(page).getByRole("heading")).toHaveText("Diagram runtime-architecture");
  });

  test("the diagram takes Wingman's theme, not the browser's", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await setUpArchitecture(page);
    await go(page, PAGE);
    // Wingman is dark by default
    await expect(frame(page).locator("#theme")).toHaveText("dark");
    await page.evaluate(() => localStorage.setItem("theme", "light"));
    await page.emulateMedia({ colorScheme: "dark" });
    await page.reload();
    await expect(frame(page).locator("#theme")).toHaveText("light");
  });
});

test.describe("The Architecture page's states", () => {
  test("a skeleton while the diagram loads", async ({ page }) => {
    const gate = held();
    await setUpArchitecture(page, { diagram: (route, slug) => gate.answer({ slug, html: diagramPage(slug) })(route) });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-diagram-loading")).toBeVisible();
    gate.release();
    await expect(frame(page).getByRole("heading")).toHaveText("Diagram runtime-architecture");
    await expect(page.getByTestId("ss-diagram-loading")).toHaveCount(0);
  });

  test("a diagram server-scan does not serve says so, and the others still open", async ({ page }) => {
    await setUpArchitecture(page, {
      diagram: (route, slug) =>
        slug === "intersight"
          ? fulfillProblem(route, 404, "NOT_FOUND", "server-scan's UI serves no diagram 'intersight' (SERVER_SCAN_UI_URL must be server-scan's UI, which serves its diagrams)")
          : json(route, { slug, html: diagramPage(slug) }),
    });
    await go(page, `${PAGE}?diagram=intersight`);
    const missing = page.getByTestId("ss-diagram-missing");
    await expect(missing).toContainText("server-scan serves no Cisco Intersight diagram");
    await expect(missing).toContainText("SERVER_SCAN_UI_URL");
    await expect(page.getByTestId("ss-diagram-frame")).toHaveCount(0);
    await tab(page, "Dell OpenManage").click();
    await expect(frame(page).getByRole("heading")).toHaveText("Diagram openmanage");
  });

  test("server-scan failing is shown as the problem", async ({ page }) => {
    await setUpArchitecture(page, {
      diagram: (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", "server-scan unreachable reading the diagram runtime-architecture: ConnectError"),
    });
    await go(page, PAGE);
    const problem = page.getByRole("alert").filter({ hasText: "The Full flow diagram could not be loaded from server-scan" });
    await expect(problem).toContainText("ConnectError");
    await expect(page.getByRole("tablist", { name: "Diagram" })).toBeVisible();
  });

  test("without server-scan the page says how to set it up", async ({ page }) => {
    await setUpArchitecture(page, {
      diagram: (route) => fulfillProblem(route, 501, "FEATURE_DISABLED", "Server Scan is not set up in this deployment: SERVER_SCAN_URL is empty."),
    });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-off")).toContainText("serverScan.url");
    await expect(page.getByRole("tablist", { name: "Diagram" })).toHaveCount(0);
  });

  test("a viewer is told the area is for admins", async ({ page }) => {
    await setUpArchitecture(page, {
      viewer: true,
      diagram: (route) => fulfillProblem(route, 403, "FORBIDDEN", "This needs the admin role."),
    });
    await page.goto(PAGE);
    await expect(page.getByTestId("ss-forbidden")).toBeVisible();
    await expect(page.getByTestId("ss-diagram-frame")).toHaveCount(0);
  });
});
