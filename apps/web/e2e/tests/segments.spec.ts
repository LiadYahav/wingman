/**
 * The Segments area (mocked; docs/notes/2026-11-13-segments-area-api.md,
 * ADR-0047): segments-manager's read-only page in Wingman's design. Site
 * cards, then every segment with the original's columns and words; status
 * tabs, site and type filters, a search and the sort, all in the URL; a
 * column picker kept per browser; copy on click; the CSV of exactly what is
 * shown; Refresh and a re-read every 30 seconds. Admins only, through the
 * top bar's area switch; off without segments-manager.
 */

import { readFile } from "node:fs/promises";
import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, go } from "../fixtures/api-handlers";
import { HERZI, HERZI_MISMATCH, SEGMENTS, forbidden, mockSegmentList, off, setUpSegments } from "../fixtures/segments";

const areas = (page: Page) => page.getByRole("navigation", { name: "Platform" });
const rows = (page: Page) => page.getByTestId("segment-row");
const cidrs = (page: Page) => rows(page).evaluateAll((trs) => trs.map((tr) => tr.getAttribute("data-segment")));
const search = (page: Page) => page.getByRole("searchbox", { name: "Search segments" });
/** Wingman's problem panels (Next's route announcer is an alert too). */
const problem = (page: Page, text: string) => page.getByRole("alert").filter({ hasText: text });
const header = (page: Page, name: string) => page.getByRole("columnheader", { name, exact: true });

test.describe("The area switch", () => {
  test("an admin switches between Wingman and Segments from the top bar", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/");
    await expect(areas(page).getByRole("link", { name: "Wingman" })).toHaveAttribute("aria-current", "page");
    await areas(page).getByRole("link", { name: "Segments" }).click();
    await expect(page).toHaveURL(/\/segments$/);
    await expect(page.getByRole("heading", { level: 1, name: "Segments" })).toBeVisible();
    await expect(areas(page).getByRole("link", { name: "Segments" })).toHaveAttribute("aria-current", "page");
    await expect(areas(page).getByRole("link", { name: "Wingman" })).not.toHaveAttribute("aria-current", "page");
    await areas(page).getByRole("link", { name: "Wingman" }).click();
    await expect(page).toHaveURL(/\/$/);
  });

  test("a viewer has no switch, and the page says it is for admins", async ({ page }) => {
    const reads = await setUpSegments(page, { viewer: true, list: forbidden, stats: forbidden, sites: forbidden });
    await go(page, "/");
    await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Clusters" })).toBeVisible();
    await expect(areas(page)).toHaveCount(0);
    await page.goto("/segments");
    await expect(page.getByTestId("segments-forbidden")).toContainText("For admins");
    await expect(rows(page)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /CSV/ })).toHaveCount(0);
    expect(reads.list.length).toBeGreaterThan(0);
  });

  test("without segments-manager the switch hides the area and the page says it is not set up", async ({ page }) => {
    await setUpSegments(page, { list: off, stats: off, sites: off });
    await go(page, "/");
    await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Clusters" })).toBeVisible();
    await expect(areas(page)).toHaveCount(0);
    await page.goto("/segments");
    await expect(page.getByTestId("segments-off")).toContainText("Segments is not set up");
  });
});

test.describe("The Segments page", () => {
  test("site cards and every segment, with the original's columns and words", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments");

    const cards = page.getByTestId("site-card");
    await expect(cards).toHaveCount(3);
    await expect(cards.nth(0).getByTestId("site-card-used")).toHaveText("4 / 5 used");
    await expect(cards.nth(0)).toContainText("HC2");
    await expect(cards.nth(0)).toContainText("UPI1");
    await expect(cards.nth(0)).not.toContainText("MCE");
    await expect(cards.nth(2)).toContainText("No allocated segments");
    await expect(page.getByTestId("segments-summary")).toHaveText("8 segments in 3 sites");

    await expect(page.getByRole("columnheader")).toHaveText([
      "Type", "Site", "VLAN ID", "EPG Name", "Network Segment", "DHCP", "Cluster", "Status",
    ]);
    await expect.poll(() => cidrs(page)).toEqual(SEGMENTS.map((s) => s.segment));

    // A holder whose file is in day1 links to Wingman's cluster page; any other is text
    const herzi = page.locator('[data-segment="10.20.44.0/24"]');
    await expect(herzi.getByRole("link", { name: HERZI })).toHaveAttribute(
      "href", `/clusters/${HERZI}?site=site1&mce=ocp4-prod-mce-site1-a`
    );
    const upi = page.locator('[data-segment="10.20.60.0/24"]');
    await expect(upi.getByTestId("segment-holders")).toHaveText(/ocp4-upi-a\s*ocp4-upi-b/);
    await expect(upi.getByRole("link")).toHaveCount(0);
    await expect(upi.locator('[data-column="dhcp"]')).toHaveText("Off");
    await expect(page.locator('[data-segment="10.20.50.0/24"]').getByRole("link")).toHaveCount(0);
    // An old record without a status is Available, as the original shows it
    const old = page.locator('[data-segment="10.20.53.0/24"]');
    await expect(old.locator('[data-column="status"]')).toHaveText("Available");
    await expect(old.locator('[data-column="dhcp"]')).toHaveText("—");
  });

  test("the filters live in the URL and come back from it", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments");
    await expect(rows(page)).toHaveCount(8);

    const status = page.getByRole("group", { name: "Status" });
    await expect(status.getByRole("button", { name: /Allocated/ })).toContainText("5");
    await status.getByRole("button", { name: /Allocated/ }).click();
    await expect(page).toHaveURL(/status=allocated/);
    await expect(rows(page)).toHaveCount(5);

    await page.getByRole("group", { name: "Site" }).getByRole("button", { name: "site1" }).click();
    await page.getByRole("group", { name: "Type" }).getByRole("button", { name: "UPI" }).click();
    await page.getByRole("group", { name: "Type" }).getByRole("button", { name: "HC" }).click();
    await expect(page).toHaveURL(/site=site1/);
    await expect(page).toHaveURL(/type=HC%2CUPI/);
    await expect.poll(() => cidrs(page)).toEqual(["10.20.42.0/24", "10.20.44.0/24", "10.20.60.0/24"]);

    await search(page).fill("herzi");
    await expect(page).toHaveURL(/q=herzi/);
    await expect.poll(() => cidrs(page)).toEqual(["10.20.44.0/24"]);
    await expect(page.getByTestId("segments-summary")).toHaveText("1 of 8 segments");

    // The same URL, opened fresh, is the same view
    await page.reload();
    await expect(rows(page)).toHaveCount(1);
    await expect(search(page)).toHaveValue("herzi");
    await expect(status.getByRole("button", { name: /Allocated/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("group", { name: "Site" }).getByRole("button", { name: "site1" })).toHaveAttribute("aria-pressed", "true");

    // A site card filters too, and pressing it again clears it
    await page.getByTestId("site-card").nth(0).click();
    await expect(page).not.toHaveURL(/site=/);

    await search(page).fill("nothing-matches-this");
    await expect(page.getByTestId("segments-no-matches")).toBeVisible();
    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect(rows(page)).toHaveCount(8);
    await expect(search(page)).toHaveValue("");
    await expect(page).toHaveURL(/\/segments$/);
  });

  test("a cluster filter from a link: exactly that holder, shown as a chip that removes it", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments?cluster=ocp4-upi-b");
    await expect.poll(() => cidrs(page)).toEqual(["10.20.60.0/24"]);
    await page.getByRole("button", { name: "Remove the cluster filter ocp4-upi-b" }).click();
    await expect(rows(page)).toHaveCount(8);
    await expect(page).toHaveURL(/\/segments$/);
  });

  test("every column sorts: ascending, descending, then segments-manager's order", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments");
    const vlan = header(page, "VLAN ID");
    await vlan.getByRole("button").click();
    await expect(page).toHaveURL(/sort=vlan_id/);
    await expect(vlan).toHaveAttribute("aria-sort", "ascending");
    await expect.poll(async () => (await cidrs(page))[0]).toBe("10.20.11.0/24");
    await vlan.getByRole("button").click();
    await expect(vlan).toHaveAttribute("aria-sort", "descending");
    await expect.poll(async () => (await cidrs(page))[0]).toBe("10.20.53.0/24");
    await vlan.getByRole("button").click();
    await expect(vlan).not.toHaveAttribute("aria-sort");
    await expect.poll(() => cidrs(page)).toEqual(SEGMENTS.map((s) => s.segment));
  });

  test("the column picker hides a column, and the browser keeps it", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments");
    await page.getByRole("button", { name: "Show or hide columns" }).click();
    await page.getByRole("checkbox", { name: "DHCP" }).click();
    await page.keyboard.press("Escape");
    await expect(header(page, "DHCP")).toHaveCount(0);
    await page.reload();
    await expect(header(page, "VLAN ID")).toBeVisible();
    await expect(header(page, "DHCP")).toHaveCount(0);
  });

  test("VLAN ID, EPG name and segment copy on click", async ({ page }) => {
    await page.addInitScript(() => {
      const copied: string[] = [];
      (window as unknown as { __copied: string[] }).__copied = copied;
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: { writeText: async (text: string) => void copied.push(text) },
      });
    });
    await setUpSegments(page);
    await go(page, "/segments");
    await page.getByRole("button", { name: "Copy VLAN ID 1418" }).click();
    await expect(page.getByText("VLAN ID copied to clipboard")).toBeVisible();
    await page.getByRole("button", { name: "Copy Segment 10.20.44.0/24" }).focus();
    await page.keyboard.press("Enter");
    expect(await page.evaluate(() => (window as unknown as { __copied: string[] }).__copied)).toEqual(["1418", "10.20.44.0/24"]);
  });

  test("the CSV holds exactly the rows and columns shown", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments?site=site1&status=allocated&sort=-vlan_id");
    await page.getByRole("button", { name: "Show or hide columns" }).click();
    await page.getByRole("checkbox", { name: "EPG Name" }).click();
    await page.keyboard.press("Escape");
    const button = page.getByRole("button", { name: "CSV of 4 shown" });
    const [download] = await Promise.all([page.waitForEvent("download"), button.click()]);
    expect(download.suggestedFilename()).toBe("segments.csv");
    const text = (await readFile(await download.path(), "utf-8")).replace(/^﻿/, "");
    expect(text.split("\r\n")).toEqual([
      "Type,Site,VLAN ID,Network Segment,DHCP,Cluster,Status",
      'UPI,site1,1460,10.20.60.0/24,Off,"ocp4-upi-a, ocp4-upi-b",Allocated',
      `HC,site1,1418,10.20.44.0/24,On,${HERZI},Allocated`,
      "HC,site1,1408,10.20.42.0/24,On,ocp4-prep-eyal-site1,Allocated",
      "INVENTORY,site1,1011,10.20.11.0/24,On,ocp4-prod-mce-site1-a,Allocated",
      "",
    ]);
  });

  test("Refresh reads segments-manager's database now, then the cards", async ({ page }) => {
    const reads = await setUpSegments(page);
    await go(page, "/segments");
    await expect(rows(page)).toHaveCount(8);
    const stats = reads.stats;
    await page.route(/\/api\/day1\/segments\?fresh=true$/, (route) => {
      reads.list.push({ fresh: true });
      return route.fulfill({ json: mockSegmentList({ segments: SEGMENTS.slice(0, 2), fresh: true }) });
    });
    await page.getByRole("button", { name: "Refresh" }).click();
    await expect(page.getByText("Read fresh from segments-manager")).toBeVisible();
    await expect(rows(page)).toHaveCount(2);
    expect(reads.list.at(-1)).toEqual({ fresh: true });
    await expect.poll(() => reads.stats).toBeGreaterThan(stats);
  });

  test("the page re-reads every 30 seconds while it is open", async ({ page }) => {
    await page.clock.install();
    const reads = await setUpSegments(page);
    await go(page, "/segments");
    await expect(rows(page)).toHaveCount(8);
    const before = reads.list.length;
    await page.clock.runFor(31_000);
    await expect.poll(() => reads.list.length).toBeGreaterThan(before);
    expect(reads.list.every((read) => !read.fresh)).toBe(true);
  });

  test("loading, then the problem when segments-manager fails", async ({ page }) => {
    await setUpSegments(page, {
      list: (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", "segments-manager answered 503 listing segments"),
    });
    await go(page, "/segments");
    await expect(problem(page, "Segments could not be loaded")).toContainText("segments-manager answered 503 listing segments");
    await expect(rows(page)).toHaveCount(0);
  });

  test("what day1 could not read is said, and the rest is shown", async ({ page }) => {
    await setUpSegments(page, {
      list: mockSegmentList({
        unreadable: ["10.20.99.0/24: vlan_id is not a number"],
        clusters_error: "GitUnavailable: GitLab answered 503",
      }),
      stats: (route) => fulfillProblem(route, 502, "DEPENDENCY_UNAVAILABLE", "segments-manager answered 500 reading stats"),
    });
    await go(page, "/segments");
    await expect(rows(page)).toHaveCount(8);
    await expect(page.getByTestId("segments-unreadable")).toContainText("10.20.99.0/24: vlan_id is not a number");
    await expect(page.getByTestId("segments-clusters-error")).toContainText("GitUnavailable: GitLab answered 503");
    await expect(problem(page, "The site cards could not be loaded")).toContainText("answered 500 reading stats");
  });

  test("a row where segments-manager disagrees with the cluster file is marked, and can be shown alone", async ({ page }) => {
    await setUpSegments(page);
    await go(page, "/segments");
    await expect(rows(page)).toHaveCount(8);
    await expect(page.locator('[data-mismatch="true"]')).toHaveCount(1);
    const herzi = page.locator('[data-segment="10.20.44.0/24"]');
    await expect(herzi).toHaveAttribute("data-mismatch", "true");
    await expect(page.getByTestId("segment-mismatch")).toHaveCount(1);

    await herzi.getByRole("button", { name: "1 disagreement with the cluster file" }).click();
    const list = page.getByTestId("segment-mismatches");
    await expect(list).toContainText(HERZI_MISMATCH);
    await expect(list.getByRole("link", { name: HERZI })).toHaveAttribute(
      "href", `/clusters/${HERZI}?site=site1&mce=ocp4-prod-mce-site1-a`
    );
    await page.keyboard.press("Escape");

    const toggle = page.getByRole("button", { name: /Disagrees with Git/ });
    await expect(toggle).toContainText("1");
    await toggle.click();
    await expect(page).toHaveURL(/mismatch=1/);
    await expect.poll(() => cidrs(page)).toEqual(["10.20.44.0/24"]);
    await page.reload();
    await expect(toggle).toHaveAttribute("aria-pressed", "true");
    await expect(rows(page)).toHaveCount(1);
  });

  test("no row disagrees: no marks and no toggle", async ({ page }) => {
    await setUpSegments(page, { list: mockSegmentList({ segments: SEGMENTS.map((s) => ({ ...s, mismatches: [] })) }) });
    await go(page, "/segments");
    await expect(rows(page)).toHaveCount(8);
    await expect(page.getByTestId("segment-mismatch")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Disagrees with Git/ })).toHaveCount(0);
  });

  test("no segments at all is an empty state, not an error", async ({ page }) => {
    await setUpSegments(page, { list: mockSegmentList({ segments: [] }) });
    await go(page, "/segments");
    await expect(page.getByTestId("segments-empty")).toContainText("No segments");
    await expect(page.getByRole("button", { name: "CSV of 0 shown" })).toBeDisabled();
  });
});
