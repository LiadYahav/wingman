/**
 * The Server Scan area (mocked; docs/notes/2026-11-13-server-scan-area-api.md,
 * ADR-0048): server-scan's UI in Wingman, page by page; here its Sites page
 * (the Servers page has its own spec). A platform in the top bar for admins
 * with server-scan configured, with server-scan's own mark and a sidebar of
 * only the pages built. The cards, counts and words are server-scan's; each
 * card and count links to the Servers page with its filter.
 */

import { test, expect, type Locator, type Page } from "@playwright/test";
import { go, held } from "../fixtures/api-handlers";
import { setUpSegments } from "../fixtures/segments";
import { NO_SERVERS, failing, forbidden, mockSites, off, setUpServerScan } from "../fixtures/server-scan";

const platform = (page: Page) => page.getByRole("navigation", { name: "Platform" });
const brand = (page: Page) => page.getByTestId("brand");
const scanNav = (page: Page) => page.getByRole("navigation", { name: "Server Scan" });
const wingmanNav = (page: Page) => page.getByRole("navigation", { name: "Main" });
const card = (page: Page, name: string) => page.getByRole("article", { name, exact: true });
const section = (page: Page, name: string) => page.getByRole("region", { name, exact: true });
const counts = (c: Locator) => c.getByTestId("ss-card-count");
/** Wingman's problem panels (Next's route announcer is an alert too). */
const problem = (page: Page, text: string) => page.getByRole("alert").filter({ hasText: text });

test.describe("The Server Scan area in the top bar", () => {
  test("an admin switches to Server Scan and back", async ({ page }) => {
    await setUpServerScan(page);
    await go(page, "/");
    await expect(platform(page).getByRole("link")).toHaveText(["Wingman", "Server Scan"]);
    await platform(page).getByRole("link", { name: "Server Scan" }).click();
    await expect(page).toHaveURL(/\/server-scan$/);
    await expect(page.getByRole("heading", { level: 1, name: "Sites" })).toBeVisible();
    await expect(platform(page).getByRole("link", { name: "Server Scan" })).toHaveAttribute("aria-current", "page");
    await platform(page).getByRole("link", { name: "Wingman" }).click();
    await expect(page).toHaveURL(/\/$/);
  });

  test("it sits after Segments when both are on", async ({ page }) => {
    await setUpSegments(page);
    await page.route("**/api/day1/server-scan/sites", (route) => route.fulfill({ json: mockSites() }));
    await go(page, "/");
    await expect(platform(page).getByRole("link")).toHaveText(["Wingman", "Segments", "Server Scan"]);
  });

  test("a viewer has no switch, and the page says it is for admins, in Wingman's chrome", async ({ page }) => {
    const { reads } = await setUpServerScan(page, { viewer: true, sites: forbidden });
    await go(page, "/");
    await expect(wingmanNav(page)).toBeVisible();
    await expect(platform(page)).toHaveCount(0);
    // A viewer's browser never asks for the area
    expect(reads()).toBe(0);
    await page.goto("/server-scan");
    await expect(page.getByTestId("ss-forbidden")).toBeVisible();
    await expect(brand(page)).toHaveAttribute("data-area", "wingman");
    await expect(scanNav(page)).toHaveCount(0);
  });

  test("without server-scan the area is hidden and its page says how to set it up", async ({ page }) => {
    const { reads } = await setUpServerScan(page, { sites: off });
    await go(page, "/");
    // The admin's browser asked, and day1 said it is off
    await expect.poll(reads).toBeGreaterThan(0);
    await expect(wingmanNav(page)).toBeVisible();
    await expect(platform(page)).toHaveCount(0);
    await page.goto("/server-scan");
    await expect(page.getByTestId("ss-off")).toContainText("serverScan.url");
    await expect(page.getByTestId("ss-card")).toHaveCount(0);
  });
});

test.describe("The Server Scan chrome", () => {
  test("server-scan's mark and name, and a sidebar of only the pages built", async ({ page }) => {
    await setUpServerScan(page);
    await go(page, "/server-scan");
    await expect(brand(page)).toHaveAttribute("data-area", "server-scan");
    await expect(brand(page)).toHaveText("Server Scan");
    await expect(brand(page)).toHaveAttribute("href", "/server-scan");
    await expect(brand(page).locator("img")).toHaveAttribute("src", "/server-scan-icon.svg");
    await expect(wingmanNav(page)).toHaveCount(0);
    await expect(scanNav(page).getByRole("link")).toHaveText(["Sites", "Servers", "Confs", "Events", "Rules & Policies", "Claude", "Architecture"]);
    await expect(scanNav(page).getByTestId("area-nav-sites")).toHaveAttribute("aria-current", "page");
    await expect(scanNav(page).getByTestId("area-nav-sites")).toHaveAttribute("href", "/server-scan");
  });

  test("each area wears its own: Wingman's logo and sidebar, then Server Scan's again", async ({ page }) => {
    await setUpServerScan(page);
    await go(page, "/server-scan");
    await platform(page).getByRole("link", { name: "Wingman" }).click();
    await expect(brand(page)).toHaveAttribute("data-area", "wingman");
    await expect(wingmanNav(page)).toBeVisible();
    await expect(scanNav(page)).toHaveCount(0);
    await platform(page).getByRole("link", { name: "Server Scan" }).click();
    await expect(brand(page)).toHaveText("Server Scan");
    await expect(scanNav(page)).toBeVisible();
  });
});

test.describe("The Sites page", () => {
  test("the header and the fleet-wide cards, in server-scan's order and words", async ({ page }) => {
    await setUpServerScan(page);
    await go(page, "/server-scan");
    await expect(page.getByTestId("ss-sites-summary")).toHaveText("38 servers across 3 sites");
    const fleet = section(page, "Fleet");
    await expect(fleet.getByRole("heading", { level: 3 })).toHaveText([
      "Across all sites", "UPI", "Hosted cluster", "MCE", "Available", "Installed",
    ]);
    await expect(fleet.getByTestId("ss-card-total")).toHaveText(["38", "6", "27", "3", "7", "25"]);
    const all = card(page, "Across all sites");
    await expect(all).toContainText("servers, every site");
    await expect(counts(all)).toHaveText(["◆2 critical", "⬟1 major", "▲1 warning", "⏸1 in maintenance", "○2 unknown"]);
    await expect(card(page, "Available")).toContainText("no cluster holds these");
    await expect(card(page, "Installed")).toContainText("in use by a cluster");
    await expect(card(page, "MCE")).toContainText("all healthy");
    // The fleet row has its own Installed and Available cards
    await expect(all.getByTestId("ss-card-state")).toHaveCount(0);
  });

  test("a card per site: its counts, installed and available, a bar per vendor; Unassigned only with servers", async ({ page }) => {
    await setUpServerScan(page);
    await go(page, "/server-scan");
    const sites = section(page, "Sites");
    await expect(sites.getByRole("heading", { level: 3 })).toHaveText(["Site 1", "Site 2", "Site 3", "Unassigned"]);
    const site1 = card(page, "Site 1");
    await expect(site1.getByTestId("ss-card-total")).toHaveText("32");
    await expect(counts(site1)).toHaveText(["◆2 critical", "⬟1 major", "▲1 warning", "⏸1 in maintenance"]);
    await expect(site1.getByTestId("ss-card-state")).toHaveText(["22 installed", "4 available"]);
    await expect(site1.getByTestId("ss-card-vendor")).toHaveText(["Dell18", "Cisco6", "HPE8", "Standalone0", "KubeVirt0"]);
    await expect(card(page, "Site 2")).toContainText("all healthy");
    // A configured site with no server is shown at 0, not left out
    const site3 = card(page, "Site 3");
    await expect(site3.getByTestId("ss-card-total")).toHaveText("0");
    await expect(site3).toContainText("empty");
    await expect(site3.getByTestId("ss-card-vendor")).toHaveCount(0);
    const unassigned = card(page, "Unassigned");
    await expect(unassigned).toContainText("no site in hostname");
    await expect(unassigned.getByTestId("ss-card-state")).toHaveText(["2 available"]);
  });

  test("every card and count links to the Servers page with its filter", async ({ page }) => {
    await setUpServerScan(page);
    await go(page, "/server-scan");
    await expect(page.getByTestId("ss-card")).toHaveCount(10);
    await expect(card(page, "UPI")).toHaveAttribute("data-filter", "installation_type=UPI");
    await expect(card(page, "UPI").getByTestId("ss-card-link")).toHaveAttribute("href", "/server-scan/servers?installation_type=UPI");
    await expect(card(page, "Across all sites").getByTestId("ss-card-link")).toHaveAttribute("href", "/server-scan/servers");
    await expect(counts(card(page, "Site 1")).first()).toHaveAttribute("href", "/server-scan/servers?site_id=site1&health_overall=CRITICAL");
    const site1 = card(page, "Site 1");
    await expect(site1).toHaveAttribute("data-filter", "site_id=site1");
    await expect(counts(site1).first()).toHaveAttribute("data-filter", "site_id=site1&health_overall=CRITICAL");
    await expect(site1.getByTestId("ss-card-count").filter({ hasText: "maintenance" })).toHaveAttribute(
      "data-filter",
      "site_id=site1&maintenance=true"
    );
    await expect(site1.getByTestId("ss-card-state").first()).toHaveAttribute("data-filter", "site_id=site1&openshift_state=INSTALLED");
  });

  test("skeleton cards while server-scan answers, then the cards", async ({ page }) => {
    const answer = held();
    await setUpServerScan(page, { sites: answer.answer(mockSites()) });
    await go(page, "/server-scan");
    await expect(page.getByTestId("ss-sites-loading")).toBeVisible();
    await expect(page.getByTestId("ss-sites-summary")).toHaveText("Loading fleet…");
    answer.release();
    await expect(page.getByTestId("ss-card")).toHaveCount(10);
    await expect(page.getByTestId("ss-sites-loading")).toHaveCount(0);
  });

  test("server-scan failing shows day1's problem, and the switch keeps the area", async ({ page }) => {
    await setUpServerScan(page, { sites: failing });
    await go(page, "/server-scan");
    await expect(problem(page, "The sites could not be loaded from server-scan")).toContainText("server-scan unreachable");
    await expect(page.getByTestId("ss-card")).toHaveCount(0);
    await expect(platform(page).getByRole("link", { name: "Server Scan" })).toHaveAttribute("aria-current", "page");
  });

  test("with no server yet, the fleet row says so and every site is still shown at 0", async ({ page }) => {
    await setUpServerScan(page, { sites: NO_SERVERS });
    await go(page, "/server-scan");
    await expect(page.getByTestId("ss-sites-empty")).toContainText("No servers yet");
    await expect(page.getByTestId("ss-sites-summary")).toHaveText("0 servers across 2 sites");
    await expect(section(page, "Sites").getByRole("heading", { level: 3 })).toHaveText(["Site 1", "Site 2"]);
    await expect(card(page, "Site 1")).toContainText("empty");
  });

  test("not polled: opening the page again within 30 seconds reads nothing new", async ({ page }) => {
    const { reads } = await setUpServerScan(page);
    await go(page, "/server-scan");
    await expect(page.getByTestId("ss-card")).toHaveCount(10);
    const after = reads();
    await platform(page).getByRole("link", { name: "Wingman" }).click();
    await platform(page).getByRole("link", { name: "Server Scan" }).click();
    await expect(page.getByTestId("ss-card")).toHaveCount(10);
    expect(reads()).toBe(after);
  });
});
