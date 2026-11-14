/**
 * The Server Scan area's Confs page (mocked; docs/notes/2026-11-13-server-scan-area-api.md
 * §10, ADR-0048's 3.29.0 amendment): server-scan's hardware catalog in
 * Wingman, its columns, words and Unmapped badge, the notice for the confs it
 * could not read, a row opened into the full spec, the search and its count,
 * read only; and the states.
 */

import { test, expect, type Page } from "@playwright/test";
import { go, held } from "../fixtures/api-handlers";
import { failing, forbidden, off } from "../fixtures/server-scan";
import { CONFS, setUpConfs } from "../fixtures/server-scan-confs";

const PAGE = "/server-scan/confs";
const scanNav = (page: Page) => page.getByRole("navigation", { name: "Server Scan" });
const table = (page: Page) => page.getByRole("table", { name: "Confs" });
const row = (page: Page, id: string) => page.locator(`[data-testid="ss-conf-row"][data-conf="${id}"]`);
const cell = (page: Page, id: string, index: number) => row(page, id).locator("td").nth(index);
/** Wingman's problem panels (Next's route announcer is an alert too). */
const problem = (page: Page, text: string) => page.getByRole("alert").filter({ hasText: text });

test.describe("The Confs page", () => {
  test("the sidebar's Confs, after Servers, opens server-scan's catalog in its columns", async ({ page }) => {
    await setUpConfs(page);
    await go(page, "/server-scan");
    await expect(scanNav(page).getByRole("link")).toHaveText(["Sites", "Servers", "Confs", "Events", "Rules & Policies", "Claude", "Architecture"]);
    await scanNav(page).getByRole("link", { name: "Confs" }).click();
    await expect(page).toHaveURL(/\/server-scan\/confs$/);
    await expect(scanNav(page).getByTestId("area-nav-confs")).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { level: 1, name: "Confs" })).toBeVisible();
    await expect(page.getByText("Server configurations (specs). Click a row for the full spec.")).toBeVisible();
    await expect(table(page).locator("thead th")).toHaveText(["Conf", "Part number", "Model", "CPU", "RAM", "Storage", "GPU", "Adapters"]);
    await expect(page.getByTestId("ss-conf-row")).toHaveCount(4);
    // server-scan's order, as it sends it
    await expect(page.getByTestId("ss-conf-row").locator("td:first-child")).toHaveText(["▸CONF200", "▸CONF202", "▸CONF-21", "▸CONF-34"]);
    await expect(page.getByTestId("ss-confs-count")).toHaveText("4 confs");
    await expect(page.getByTestId("ss-confs-unreadable")).toHaveText("1 stored conf could not be read and is not listed: CONF-99");
  });

  test("read only: why in the heading's tooltip, and nothing to press but the search and the rows", async ({ page }) => {
    await setUpConfs(page);
    await go(page, PAGE);
    const about = page.getByTestId("ss-confs-about");
    await expect(about).toHaveAccessibleName("About Confs");
    await about.hover();
    await expect(page.locator("[data-slot=tooltip-content][data-open]")).toContainText("another system writes server-scan's confs collection");
    await expect(page.getByRole("main").getByRole("button")).toHaveText(["", "▸", "▸", "▸", "▸"]);
    await expect(page.getByRole("main").getByRole("textbox")).toHaveCount(0);
    await expect(page.getByRole("main").getByRole("searchbox")).toHaveCount(1);
  });

  test("a row in server-scan's words: CPU, RAM, storage, GPUs, adapters; Unmapped; an unread value muted", async ({ page }) => {
    await setUpConfs(page);
    await go(page, PAGE);
    await expect(cell(page, "CONF200", 1)).toHaveText("210-AZKL");
    await expect(cell(page, "CONF200", 2)).toHaveText("PowerEdge R650");
    await expect(cell(page, "CONF200", 3)).toHaveText("2× Intel Xeon Gold 633864 cores · 128 threads · 2.0 GHz");
    await expect(cell(page, "CONF200", 4)).toHaveText("512 GiB16 × 32 GB DDR4");
    await expect(cell(page, "CONF200", 5)).toHaveText("4.8 TB4 drives");
    await expect(cell(page, "CONF200", 6)).toHaveText("—");
    await expect(cell(page, "CONF200", 7)).toHaveText("1× 2-port 25 Gb/s1× 2-port 1 Gb/s");
    await expect(cell(page, "CONF202", 6)).toHaveText("8× NVIDIA H200 SXM141 GB each");
    // No part number: no catalog entry
    const unmapped = cell(page, "CONF-21", 1).getByTestId("ss-conf-unmapped");
    await expect(unmapped).toHaveText("Unmapped");
    await expect(unmapped).toHaveAttribute("title", /No catalog entry matches this conf/);
    await expect(cell(page, "CONF-21", 4)).toHaveText("512 GiB16 × 32 GB type unread");
    // A failed memory scan is said, never 0 GiB; nothing at all is a dash
    await expect(cell(page, "CONF-34", 4)).toHaveText("not read (scan failed)");
    await expect(cell(page, "CONF-34", 5)).toHaveText("—");
    await expect(cell(page, "CONF-34", 7)).toHaveText("—");
  });

  test("a row opens into its full spec, by its ▸ or a click on the row; several stay open", async ({ page }) => {
    await setUpConfs(page);
    await go(page, PAGE);
    await page.getByRole("button", { name: "Show details of CONF-21" }).click();
    const detail = page.getByTestId("ss-conf-detail");
    await expect(detail).toHaveCount(1);
    await expect(detail.getByRole("region", { name: "Identity" })).toHaveText("IdentityConf ID: CONF-21Part number: —Model: PowerEdge R650");
    const cpu = detail.getByRole("region", { name: "CPU" });
    await expect(cpu).toContainText("2 sockets × 32 cores");
    await expect(cpu).toContainText("128 threads (HT)");
    await expect(cpu).toContainText("2.0 GHz base, 3.2 GHz max");
    await expect(cpu).toContainText("Cache: L1 2.5 MB · L2 40 MB · L3 48 MB");
    await expect(detail.getByRole("region", { name: "Memory" })).toContainText("16 × 32 GB DIMMs");
    await expect(detail.getByRole("region", { name: "Memory" })).toContainText("Type: not read (DIMM read failed)");
    const parts = detail.getByRole("region", { name: "Storage, GPU and adapters" });
    await expect(parts).toContainText("2× 0.96 TB unknown");
    await expect(parts).toContainText("Adapters (1):1× 2-port 25 Gb/s");
    await expect(page.getByRole("button", { name: "Hide details of CONF-21" })).toHaveAttribute("aria-expanded", "true");
    // A click on the row opens it too
    await cell(page, "CONF202", 2).click();
    await expect(page.getByTestId("ss-conf-detail")).toHaveCount(2);
    await expect(page.getByTestId("ss-conf-detail").nth(0)).toContainText("GPUs (8):8× NVIDIA H200 SXM141 GB VRAM per GPU");
    await page.getByRole("button", { name: "Hide details of CONF-21" }).click();
    await expect(page.getByTestId("ss-conf-detail")).toHaveCount(1);
    await row(page, "CONF-34").click();
    await expect(page.getByTestId("ss-conf-detail").last()).toContainText("not read (scan failed)");
    await expect(page.getByTestId("ss-conf-detail").last()).toContainText("No disks");
  });

  test("the search keeps the confs every word matches, in server-scan's order, and says how many", async ({ page }) => {
    await setUpConfs(page);
    await go(page, PAGE);
    const search = page.getByRole("searchbox", { name: "Search" });
    await search.fill("h200");
    await expect(page.getByTestId("ss-conf-row")).toHaveCount(1);
    await expect(row(page, "CONF202")).toBeVisible();
    await expect(page.getByTestId("ss-confs-count")).toHaveText("1 of 4 confs");
    await search.fill("r650 unknown");
    await expect(page.getByTestId("ss-conf-row")).toHaveCount(1);
    await expect(row(page, "CONF-21")).toBeVisible();
    await search.fill("AMD");
    await expect(page.getByTestId("ss-conf-row").locator("td:first-child")).toHaveText(["▸CONF-34"]);
    await search.fill("supermicro");
    await expect(page.getByTestId("ss-conf-row")).toHaveCount(0);
    await expect(table(page)).toContainText("No conf matches the search.");
    await expect(page.getByTestId("ss-confs-count")).toHaveText("0 of 4 confs");
    await search.press("Escape");
    await expect(page.getByTestId("ss-conf-row")).toHaveCount(4);
  });
});

test.describe("The Confs page's states", () => {
  test("skeleton rows while server-scan answers, then the catalog", async ({ page }) => {
    const answer = held();
    await setUpConfs(page, { confs: answer.answer(CONFS) });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-confs-loading")).toBeVisible();
    answer.release();
    await expect(page.getByTestId("ss-conf-row")).toHaveCount(4);
    await expect(page.getByTestId("ss-confs-loading")).toHaveCount(0);
  });

  test("no conf stored: server-scan's words, and the unreadable ones still named", async ({ page }) => {
    await setUpConfs(page, { confs: { items: [], unreadable: ["CONF-98", "CONF-99"] } });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-confs-empty")).toContainText("No confs are stored.");
    await expect(page.getByTestId("ss-confs-unreadable")).toHaveText("2 stored confs could not be read and are not listed: CONF-98, CONF-99");
    await expect(table(page)).toHaveCount(0);
  });

  test("every conf read: no notice", async ({ page }) => {
    await setUpConfs(page, { confs: { ...CONFS, unreadable: [] } });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-conf-row")).toHaveCount(4);
    await expect(page.getByTestId("ss-confs-unreadable")).toHaveCount(0);
  });

  test("server-scan failing shows day1's problem", async ({ page }) => {
    await setUpConfs(page, { confs: failing });
    await go(page, PAGE);
    await expect(problem(page, "The confs could not be loaded from server-scan")).toContainText("server-scan unreachable");
    await expect(page.getByTestId("ss-conf-row")).toHaveCount(0);
  });

  test("without server-scan the page says how to set it up", async ({ page }) => {
    await setUpConfs(page, { confs: off, sites: off });
    await page.goto(PAGE);
    await expect(page.getByTestId("ss-off")).toContainText("serverScan.url");
    await expect(table(page)).toHaveCount(0);
  });

  test("a viewer is told it is for admins", async ({ page }) => {
    await setUpConfs(page, { confs: forbidden, sites: forbidden, viewer: true });
    await page.goto(PAGE);
    await expect(page.getByTestId("ss-forbidden")).toBeVisible();
    await expect(table(page)).toHaveCount(0);
  });

  test("not polled: opening the page again within 30 seconds reads nothing new", async ({ page }) => {
    const { reads } = await setUpConfs(page);
    await go(page, PAGE);
    await expect(page.getByTestId("ss-conf-row")).toHaveCount(4);
    const after = reads();
    await scanNav(page).getByRole("link", { name: "Servers" }).click();
    await expect(page).toHaveURL(/\/server-scan\/servers$/);
    await scanNav(page).getByRole("link", { name: "Confs" }).click();
    await expect(page.getByTestId("ss-conf-row")).toHaveCount(4);
    expect(reads()).toBe(after);
  });
});
