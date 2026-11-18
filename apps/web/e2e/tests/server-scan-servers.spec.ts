/**
 * The Server Scan area's Servers page (mocked; docs/notes/2026-11-13-server-scan-area-api.md
 * §8, ADR-0048's 3.23.0 amendment): server-scan's fleet page in Wingman, its
 * columns, words, filters, search, sort, cluster sidebar, export and paging,
 * every filter in the URL under server-scan's names; the Sites counts link
 * here; and its one write, a server's maintenance on and off.
 */

import { readFile } from "node:fs/promises";
import { test, expect, type Page } from "@playwright/test";
import { fulfillProblem, go, held } from "../fixtures/api-handlers";
import { scrollState } from "../fixtures/scroll";
import { failing, forbidden, off } from "../fixtures/server-scan";
import { mockFetchNow, nodeRecord } from "../fixtures/server-scan-server";
import { FLEET, bigFleet, mockMaintenance, mockServers, setUpServers } from "../fixtures/server-scan-servers";
import { readXlsx } from "../fixtures/xlsx";

const PAGE = "/server-scan/servers";
const rows = (page: Page) => page.getByTestId("ss-server-row");
const names = (page: Page) => rows(page).evaluateAll((trs) => trs.map((tr) => tr.getAttribute("data-server")));
const row = (page: Page, name: string) => page.locator(`[data-testid="ss-server-row"][data-server="${name}"]`);
const query = (page: Page) => new URL(page.url()).search.replace(/^\?/, "");
const params = (page: Page) => new URL(page.url()).searchParams;
const dropdown = (page: Page, label: string) => page.getByTestId(`ss-filter-${label.toLowerCase()}`);
const option = (page: Page, label: string, value: string) =>
  page.getByRole("group", { name: `${label} values` }).getByRole("checkbox", { name: new RegExp(`^${value}\\b`) });
const summary = (page: Page) => page.getByTestId("ss-servers-summary");
const chips = (page: Page) => page.getByTestId("ss-active-filters").getByRole("button", { name: /^(?!Clear filters)/ });

/** Tick one value of a dropdown, then close it. */
async function tick(page: Page, label: string, value: string) {
  await dropdown(page, label).click();
  await option(page, label, value).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("group", { name: `${label} values` })).toHaveCount(0);
}

test.describe("The Servers page", () => {
  test("the sidebar's Servers entry, the header and the table in server-scan's columns and words", async ({ page }) => {
    await setUpServers(page);
    await go(page, "/server-scan");
    const nav = page.getByRole("navigation", { name: "Server Scan" });
    await expect(nav.getByRole("link")).toHaveText(["Sites", "Servers", "Confs", "Events", "Jobs", "Rules & Policies", "Claude", "Architecture"]);
    await nav.getByRole("link", { name: "Servers" }).click();
    await expect(page).toHaveURL(/\/server-scan\/servers$/);
    await expect(nav.getByTestId("area-nav-servers")).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { level: 1, name: "Servers" })).toBeVisible();
    await expect(summary(page)).toHaveText("12 servers");
    await expect(page.getByTestId("ss-servers-updated")).toContainText("Updated 13/11/2026");
    // server-scan v6.6.0: the first column is each row's Fetch now, its header for screen readers
    await expect(page.getByRole("table", { name: "Servers" }).locator("thead th")).toHaveText([
      "Fetch now", "Name", "BMC", "Installation", "MCE", "Cluster", "Model", "State", "Maintenance",
    ]);
    // Sorted by name, naturally
    await expect.poll(async () => (await names(page))[0]).toBe("hpe-dl380-site2-stale-10");
    const node = row(page, "ocp-dell-r660-site1-node-01");
    const bmc = node.getByRole("link", { name: "Open BMC console for ocp-dell-r660-site1-node-01" });
    await expect(bmc).toHaveAttribute("href", "https://192.0.2.101");
    // server-scan v6.2.0: the address first on hover, and a copy button beside the console
    await expect(bmc).toHaveAttribute("title", "192.0.2.101 — open BMC console");
    const copyBmc = node.getByRole("button", { name: "Copy BMC address 192.0.2.101" });
    await expect(copyBmc).toHaveAttribute("title", "192.0.2.101 — copy");
    // One twin has no BMC read: neither its console nor its copy
    await expect(row(page, "ocp-twin").getByRole("button", { name: /Copy BMC address/ })).toHaveCount(1);
    await expect(node.locator('[data-column="openshift_state"]')).toHaveText("Installed");
    await expect(node.locator('[data-column="mce_name"]')).toHaveText("ocp4-prod-mce-site1-a");
    await expect(node.locator('[data-column="health"]')).toHaveText("●Healthy");
    // The name opens the server's page (server-scan-server.spec.ts), its copy button beside it
    await expect(node.getByRole("link", { name: "ocp-dell-r660-site1-node-01", exact: true })).toHaveAttribute("href", "/server-scan/servers/srv_ocp-dell-r660-site1-node-01");
    await expect(node.getByRole("button", { name: "Copy server name ocp-dell-r660-site1-node-01" })).toBeVisible();
    await expect(row(page, "ocp-dell-r760-site1-free-06").getByTestId("ss-reservation")).toHaveText("→ocp4-prod-mce-site1-b");
    await expect(row(page, "ucs-cisco-site2-upi-08")).toContainText("Contested with ocp4-upi-other");
    const maint = row(page, "ocp-dell-r660-site1-node-03").getByTestId("ss-maint-chip");
    await expect(maint).toHaveText("⏸Maint");
    await expect(maint).toHaveAttribute("title", "Replacing PSU 2 — INC-4417 - by API token (admin)");
    await expect(row(page, "ocp-dell-r660-site1-node-04").getByTestId("ss-maint-chip")).toHaveText("◇Donor");
    await expect(row(page, "hpe-dl380-site2-stale-10")).toContainText(/Stale \d+d/);
    await expect(row(page, "ocp-dell-r660-site2-node-09")).toContainText("Name mismatch");
  });

  test("the dropdowns filter with server-scan's counts, kept in the URL, each a chip that removes it", async ({ page }) => {
    await setUpServers(page);
    await go(page, PAGE);
    await expect(dropdown(page, "Vendor")).toHaveText("All (12)");
    await dropdown(page, "Vendor").click();
    await expect(page.getByRole("group", { name: "Vendor values" }).getByRole("checkbox")).toHaveText([
      "dell8", "cisco2", "hp1", "standalone1", "kubevirt0",
    ]);
    await page.keyboard.press("Escape");
    await tick(page, "Vendor", "cisco");
    await expect(rows(page)).toHaveCount(2);
    await expect.poll(() => query(page)).toBe("vendor=cisco");
    await expect(summary(page)).toHaveText("2 servers");
    // Several values of one dropdown are OR, the dropdowns AND
    await tick(page, "Vendor", "hp");
    await expect(rows(page)).toHaveCount(3);
    await tick(page, "Site", "Site 2");
    await expect.poll(() => query(page)).toBe("vendor=cisco&vendor=hp&site_id=site2");
    await expect(chips(page)).toHaveText(["Vendor cisco", "Vendor hp", "Site Site 2"]);
    await chips(page).filter({ hasText: "Vendor hp" }).click();
    await expect.poll(() => query(page)).toBe("vendor=cisco&site_id=site2");
    // Health's Maintenance keeps only the servers in maintenance
    await page.getByRole("button", { name: "Clear filters" }).click();
    await tick(page, "Health", "Maintenance");
    await expect.poll(() => query(page)).toBe("maintenance=true");
    await expect.poll(() => names(page)).toEqual(["ocp-dell-r660-site1-node-03", "ocp-dell-r660-site1-node-04"]);
    await expect(chips(page)).toHaveText(["Maintenance only"]);
  });

  test("server-scan v6.3.0: the Type dropdown, between Source and Site, keeps physical servers or VMs, in the URL as server_type", async ({ page }) => {
    const vm = { ...FLEET[0], id: "srv_vm-01", name: "vm-kubevirt-site1-01", vendor: "kubevirt", server_type: "vm", source_provider: "KUBEVIRT" } as const;
    await setUpServers(page, { servers: mockServers([...FLEET, vm]) });
    await go(page, PAGE);
    await expect(page.locator('[data-testid^="ss-filter-"]')).toHaveText([
      "All (13)", "All (13)", "All (13)", "All sites (13)", "All (13)", "All (13)", "All (13)",
    ]);
    await expect(page.locator('[data-testid^="ss-filter-"]').nth(2)).toHaveAttribute("data-testid", "ss-filter-type");
    await dropdown(page, "Type").click();
    await expect(page.getByRole("group", { name: "Type values" }).getByRole("checkbox")).toHaveText(["Physical12", "VM1"]);
    await page.keyboard.press("Escape");
    await tick(page, "Type", "VM");
    await expect.poll(() => query(page)).toBe("server_type=vm");
    await expect.poll(() => names(page)).toEqual([vm.name]);
    await expect(chips(page)).toHaveText(["Type VM"]);
    await chips(page).click();
    await expect.poll(() => query(page)).toBe("");
    await expect(rows(page)).toHaveCount(13);
  });

  test("server-scan v6.3.0: a ticked severity leaves out servers in maintenance unless Maintenance is ticked too, and its count follows", async ({ page }) => {
    const healthy = FLEET.filter((s) => s.health === "HEALTHY");
    const inService = healthy.filter((s) => !s.maintenance.enabled).map((s) => s.name);
    const DONOR = "ocp-dell-r660-site1-node-04";
    expect(healthy.filter((s) => s.maintenance.enabled).map((s) => s.name)).toEqual([DONOR]);
    await setUpServers(page);
    await go(page, PAGE);
    await dropdown(page, "Health").click();
    await expect(option(page, "Health", "HEALTHY")).toHaveText(`HEALTHY${inService.length}`);
    await expect(option(page, "Health", "Maintenance")).toHaveText("Maintenance2");
    await page.keyboard.press("Escape");
    await tick(page, "Health", "HEALTHY");
    await expect.poll(() => query(page)).toBe("health_overall=HEALTHY");
    await expect.poll(async () => (await names(page)).sort()).toEqual([...inService].sort());
    await expect(summary(page)).toHaveText(`${inService.length} servers`);
    await expect(row(page, DONOR)).toHaveCount(0);
    // Ticking Maintenance adds the Healthy server in maintenance, and its count said so
    await dropdown(page, "Health").click();
    await expect(option(page, "Health", "HEALTHY")).toHaveText(`HEALTHY${inService.length}`);
    await expect(option(page, "Health", "Maintenance")).toHaveText("Maintenance1");
    await page.keyboard.press("Escape");
    await tick(page, "Health", "Maintenance");
    await expect.poll(() => query(page)).toBe("health_overall=HEALTHY&maintenance=true");
    await expect.poll(() => names(page)).toEqual([DONOR]);
    // Every other severity too: the Warning server in maintenance needs Maintenance ticked
    const PAUSED_WARNING = "ocp-dell-r660-site1-node-03";
    await page.getByRole("button", { name: "Clear filters" }).click();
    await dropdown(page, "Health").click();
    await expect(option(page, "Health", "WARNING")).toHaveText("WARNING0");
    await page.keyboard.press("Escape");
    await tick(page, "Health", "WARNING");
    await expect(row(page, PAUSED_WARNING)).toHaveCount(0);
    await tick(page, "Health", "Maintenance");
    await expect.poll(() => names(page)).toEqual([PAUSED_WARNING]);
  });

  test("the toggles, with server-scan's tooltips and counts", async ({ page }) => {
    await setUpServers(page);
    await go(page, PAGE);
    const toggles = page.getByRole("group", { name: "Toggles" });
    await expect(toggles.locator("label")).toHaveText(["Stale", "Duplicate Name", "Duplicate Server", "Name mismatch", "Donor"]);
    await toggles.getByText("Duplicate Name").click();
    await expect.poll(() => names(page)).toEqual(["ocp-twin", "ocp-twin"]);
    await expect(toggles.locator("label").nth(1)).toHaveText("Duplicate Name(2)");
    await expect.poll(() => query(page)).toBe("duplicate=true");
    await toggles.getByText("Duplicate Name").click();
    await toggles.getByText("Donor").click();
    await expect.poll(() => names(page)).toEqual(["ocp-dell-r660-site1-node-04"]);
    await expect(toggles.locator("label").nth(4)).toHaveAttribute("title", /donor/);
  });

  test("Wingman's Model column filter, in the URL as f.model", async ({ page }) => {
    await setUpServers(page);
    await go(page, PAGE);
    await page.getByRole("button", { name: /^Filter Model/ }).click();
    const values = page.getByTestId("column-filter").getByRole("group", { name: "Model values" }).getByRole("checkbox");
    await expect(values).toHaveText(["PowerEdge R660", "PowerEdge R760", "ProLiant DL380", "UCS C240", "(Blank)"]);
    await page.getByTestId("column-filter").getByRole("checkbox", { name: "(Select all)" }).click();
    await page.getByTestId("column-filter").getByRole("checkbox", { name: "UCS C240", exact: true }).click();
    await page.getByTestId("column-filter").getByRole("button", { name: "Apply" }).click();
    await expect.poll(() => query(page)).toBe("f.model=UCS+C240");
    await expect(rows(page)).toHaveCount(2);
    await expect(chips(page)).toHaveText(["Model UCS C240"]);
    // The dropdowns count under it
    await expect(dropdown(page, "Vendor")).toHaveText("All (2)");
  });

  test("a URL opens its view, and the view's changes reach the URL", async ({ page }) => {
    await setUpServers(page);
    await go(page, `${PAGE}?vendor=dell&site_id=site1&installation_type=HOSTED_CLUSTER&sort=health&sort_desc=true`);
    await expect(dropdown(page, "Vendor")).toHaveText("dell");
    await expect(dropdown(page, "Site")).toHaveText("Site 1");
    await expect(dropdown(page, "Classification")).toHaveText("HOSTED_CLUSTER");
    await expect(chips(page)).toHaveText(["Vendor dell", "Site Site 1", "Classification HOSTED_CLUSTER"]);
    // State descending: worst first
    await expect(rows(page).first().locator('[data-column="health"]')).toContainText("Critical");
    await page.reload();
    await expect(chips(page)).toHaveCount(3);
    await expect(rows(page)).toHaveCount(6);
    // Clear keeps the sort
    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect.poll(() => query(page)).toBe("sort=health&sort_desc=true");
  });

  test("search: plain text, a whole value in quotes, a regular expression, and a bad one", async ({ page }) => {
    await setUpServers(page);
    await go(page, PAGE);
    const box = page.getByRole("searchbox", { name: "Search servers" });
    await expect(box).toHaveAttribute("title", /between slashes is a regular expression/);
    await box.fill("cisco");
    await expect(rows(page)).toHaveCount(2);
    await expect.poll(() => params(page).get("search")).toBe("cisco");
    await box.fill('"DL0101"');
    await expect.poll(() => names(page)).toEqual(["ocp-dell-r660-site1-node-01"]);
    await box.fill("/node-0[12]$/");
    await expect(rows(page)).toHaveCount(2);
    // A held reservation's MCE is searched too
    await box.fill("mce-site1-b");
    await expect.poll(() => names(page)).toEqual(["ocp-dell-r760-site1-free-06"]);
    await box.fill("/node-(/");
    await expect(page.getByTestId("ss-search-error")).toContainText("Invalid regex");
    await expect(rows(page)).toHaveCount(12);
  });

  test("sorting by a header: ascending, then descending; State worst first", async ({ page }) => {
    await setUpServers(page);
    await go(page, PAGE);
    const header = (name: string) => page.getByRole("table", { name: "Servers" }).getByRole("button", { name, exact: true });
    await header("Model").click();
    await expect.poll(() => query(page)).toBe("sort=model");
    await expect.poll(async () => (await names(page)).at(-1)).toBe("ocp-twin");
    await header("Model").click();
    await expect.poll(() => query(page)).toBe("sort=model&sort_desc=true");
    await header("State").click();
    await expect.poll(() => query(page)).toBe("sort=health&sort_desc=true");
    await expect(rows(page).first()).toHaveAttribute("data-server", "ocp-dell-r660-site1-node-02");
    // BMC does not sort
    await expect(page.getByRole("table", { name: "Servers" }).getByRole("button", { name: "BMC", exact: true })).toHaveCount(0);
  });

  test("the cluster sidebar: MCEs, hosted and UPI clusters with counts, kept in the URL, and folded away", async ({ page }) => {
    await setUpServers(page);
    await go(page, PAGE);
    const sidebar = page.getByRole("complementary", { name: "Cluster filters" });
    await expect(sidebar.getByRole("region", { name: "MCE" }).getByRole("checkbox")).toHaveText(["ocp4-prod-mce-site1-a6"]);
    await expect(sidebar.getByRole("region", { name: "Hosted clusters" }).getByRole("checkbox")).toHaveText(["ocp4-prod-lark-site15"]);
    await expect(sidebar.getByRole("region", { name: "UPI clusters" }).getByRole("checkbox")).toHaveText(["ocp4-upi-orca2"]);
    await sidebar.getByRole("checkbox", { name: /^ocp4-upi-orca/ }).click();
    await expect.poll(() => query(page)).toBe("cluster=ocp4-upi-orca");
    await expect(rows(page)).toHaveCount(2);
    // Counts follow the other filters: the MCE has nothing in the UPI cluster
    await expect(sidebar.getByRole("region", { name: "MCE" }).getByRole("checkbox")).toHaveText(["ocp4-prod-mce-site1-a0"]);
    await sidebar.getByRole("button", { name: "Hide filters" }).click();
    await expect(page.getByRole("button", { name: "Clusters (1)" })).toBeVisible();
    await page.getByRole("button", { name: "Clusters (1)" }).click();
    await expect(sidebar).toBeVisible();
  });

  test("export: every server the filters keep, as server-scan's Excel file and as CSV", async ({ page }) => {
    await setUpServers(page, { servers: mockServers(bigFleet(120)) });
    await go(page, `${PAGE}?vendor=dell`);
    await expect(summary(page)).toHaveText("60 servers");
    const download = async (name: RegExp) => {
      const [file] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name }).click()]);
      return { name: file.suggestedFilename(), path: await file.path() };
    };
    const day = new Date().toISOString().slice(0, 10);
    const csv = await download(/^CSV$/);
    expect(csv.name).toBe(`inventory-${day}.csv`);
    const lines = (await readFile(csv.path, "utf-8")).replace(/^﻿/, "").trim().split("\r\n");
    expect(lines[0]).toBe("Name,Vendor,BMC address,Model,Serial,SPT,Installation,MCE,Cluster,State");
    // Every page, not only the 50 shown
    expect(lines).toHaveLength(61);
    const xlsx = await download(/Export Excel/);
    expect(xlsx.name).toBe(`inventory-${day}.xlsx`);
    const book = await readXlsx(xlsx.path);
    expect(book.sheets).toEqual(["Servers"]);
    expect(book.rows).toHaveLength(61);
    expect(book.rows[1].slice(0, 2)).toEqual(["srv-0000", "dell"]);
  });

  test("the Sites page's counts open the Servers page with their filter", async ({ page }) => {
    await setUpServers(page);
    await go(page, "/server-scan");
    const site1 = page.getByRole("article", { name: "Site 1", exact: true });
    await site1.getByTestId("ss-card-count").filter({ hasText: "critical" }).click();
    await expect(page).toHaveURL(/\/server-scan\/servers\?site_id=site1&health_overall=CRITICAL$/);
    await expect.poll(() => names(page)).toEqual(["ocp-dell-r660-site1-node-02"]);
    await expect(chips(page)).toHaveText(["Site Site 1", "Health CRITICAL"]);
    await page.goBack();
    await page.getByRole("article", { name: "UPI", exact: true }).getByTestId("ss-card-link").click();
    await expect(page).toHaveURL(/\/server-scan\/servers\?installation_type=UPI$/);
    await expect(rows(page)).toHaveCount(2);
  });

  test("paging 3,100 servers 50 at a time; a filter change goes back to page 1 and stays quick", async ({ page }) => {
    await setUpServers(page, { servers: mockServers(bigFleet(3100)) });
    await go(page, PAGE);
    await expect(rows(page)).toHaveCount(50);
    await expect(page.getByTestId("pager-status")).toHaveText("Page 1 of 62");
    await page.getByRole("button", { name: "Next" }).click();
    await expect.poll(() => query(page)).toBe("page=2");
    await expect(rows(page).first()).toHaveAttribute("data-server", "srv-0050");
    const started = Date.now();
    await tick(page, "Vendor", "cisco");
    await expect(page.getByTestId("pager-status")).toHaveText("Page 1 of 16");
    expect(Date.now() - started).toBeLessThan(3_000);
    await expect.poll(() => query(page)).toBe("vendor=cisco");
    await expect(rows(page)).toHaveCount(50);
  });
});

test.describe("The Servers page's states", () => {
  test("server-scan v6.4.0: the table scrolls inside its own box, its header pinned, and the page does not", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await setUpServers(page, { servers: mockServers(bigFleet(3100)) });
    await go(page, PAGE);
    await expect(rows(page)).toHaveCount(50);
    const box = '[data-testid="ss-servers-box"] > div';
    await expect.poll(async () => (await scrollState(page, box)).pageScrolls).toBe(false);
    expect((await scrollState(page, box)).boxScrolls).toBe(true);
    await page.locator(box).hover();
    await page.mouse.wheel(0, 900);
    await expect.poll(async () => (await scrollState(page, box)).boxTop).toBeGreaterThan(0);
    const scrolled = await scrollState(page, box);
    expect([scrolled.mainTop, scrolled.pinned]).toEqual([0, true]);
    // The pager stays in view under the box
    await expect(page.getByTestId("pager-status")).toBeInViewport();
  });

  test("skeleton rows while server-scan answers, then the rows", async ({ page }) => {
    const answer = held();
    await setUpServers(page, { servers: answer.answer(mockServers()) });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-servers-loading")).toBeVisible();
    answer.release();
    await expect(rows(page)).toHaveCount(12);
  });

  test("for admins: a viewer sees why", async ({ page }) => {
    await setUpServers(page, { servers: forbidden });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-forbidden")).toContainText("For admins");
  });

  test("not set up: how to turn it on", async ({ page }) => {
    await setUpServers(page, { servers: off });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-off")).toContainText("serverScan.url");
  });

  test("server-scan failing shows day1's problem", async ({ page }) => {
    await setUpServers(page, { servers: failing });
    await go(page, PAGE);
    await expect(page.getByRole("alert").filter({ hasText: "The servers could not be loaded from server-scan" })).toContainText("server-scan unreachable");
  });

  test("no server yet, and nothing matching with Clear filters", async ({ page }) => {
    await setUpServers(page, { servers: mockServers([]) });
    await go(page, PAGE);
    await expect(page.getByTestId("ss-servers-empty")).toContainText("No servers yet");
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await setUpServers(page);
    await go(page, `${PAGE}?vendor=kubevirt`);
    await expect(page.getByTestId("ss-servers-no-matches")).toContainText("No servers match: Vendor kubevirt.");
    await page.getByTestId("ss-servers-no-matches").getByRole("button", { name: "Clear filters" }).click();
    await expect(rows(page)).toHaveCount(12);
    expect(FLEET).toHaveLength(12);
  });
});

test.describe("Maintenance on and off", () => {
  const toggle = (page: Page, name: string) => row(page, name).getByTestId("ss-maintenance-toggle");
  const dialog = (page: Page) => page.getByTestId("ss-maintenance-dialog");

  test("on: server-scan's dialog asks why, with the expected end, and the row shows it", async ({ page }) => {
    const answer = mockServers(structuredClone(FLEET));
    await setUpServers(page, { servers: answer });
    const calls = await mockMaintenance(page, answer);
    await go(page, PAGE);
    const button = toggle(page, "ocp-dell-r660-site1-node-01");
    await expect(button).toHaveAccessibleName("Put ocp-dell-r660-site1-node-01 into maintenance");
    await button.click();
    await expect(dialog(page).getByRole("heading")).toHaveText("Put into maintenance");
    await expect(dialog(page)).toContainText("ocp-dell-r660-site1-node-01");
    await expect(dialog(page)).toContainText("Why is it going into maintenance?");
    await expect(dialog(page)).toContainText("Include the word “donor” to mark it as a parts donor.");
    await expect(dialog(page).getByRole("textbox", { name: /^Why is it going/ })).toHaveAttribute("placeholder", "Replacing PSU 2 — INC-4417");
    // Cancel sends nothing
    await dialog(page).getByRole("button", { name: "Cancel" }).click();
    await expect(dialog(page)).toHaveCount(0);
    expect(calls).toHaveLength(0);
    await button.click();
    await dialog(page).getByRole("textbox", { name: /^Why is it going/ }).fill("  Replacing DIMM A1 — INC-5000  ");
    await dialog(page).getByLabel(/Expected end/).fill("2026-11-14T16:30");
    await dialog(page).getByRole("button", { name: "Start maintenance" }).click();
    await expect(dialog(page)).toHaveCount(0);
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("PUT");
    expect(calls[0].id).toBe("srv_ocp-dell-r660-site1-node-01");
    const body = calls[0].body as { reason: string; expected_end: string };
    expect(body.reason).toBe("Replacing DIMM A1 — INC-5000");
    expect(new Date(body.expected_end).getTime()).toBe(new Date(2026, 10, 14, 16, 30).getTime());
    const chip = row(page, "ocp-dell-r660-site1-node-01").getByTestId("ss-maint-chip");
    await expect(chip).toHaveText("⏸Maint");
    await expect(chip).toHaveAttribute("title", "Replacing DIMM A1 — INC-5000 - by API token (admin)");
    await expect(toggle(page, "ocp-dell-r660-site1-node-01")).toHaveAttribute("data-state", "on");
  });

  test("an empty reason and no expected end are sent as null, as server-scan allows", async ({ page }) => {
    const answer = mockServers(structuredClone(FLEET));
    await setUpServers(page, { servers: answer });
    const calls = await mockMaintenance(page, answer);
    await go(page, PAGE);
    await toggle(page, "ocp-dell-r660-site1-node-01").click();
    await dialog(page).getByRole("button", { name: "Start maintenance" }).click();
    await expect(dialog(page)).toHaveCount(0);
    expect(calls[0].body).toEqual({ reason: null, expected_end: null });
  });

  test("off: one click ends it, as server-scan", async ({ page }) => {
    const answer = mockServers(structuredClone(FLEET));
    await setUpServers(page, { servers: answer });
    const calls = await mockMaintenance(page, answer);
    await go(page, PAGE);
    const button = toggle(page, "ocp-dell-r660-site1-node-03");
    await expect(button).toHaveAccessibleName("End maintenance on ocp-dell-r660-site1-node-03");
    await button.click();
    await expect(row(page, "ocp-dell-r660-site1-node-03").getByTestId("ss-maint-chip")).toHaveCount(0);
    expect(calls).toEqual([{ method: "DELETE", id: "srv_ocp-dell-r660-site1-node-03", body: null }]);
    await expect(dialog(page)).toHaveCount(0);
  });

  test("without server-scan's admin token the toggle is greyed out with day1's one line", async ({ page }) => {
    const detail =
      "Maintenance needs server-scan's admin token: add the key admin-token to the server-scan Secret and restart day1 (SERVER_SCAN_ADMIN_TOKEN).";
    const answer = mockServers(structuredClone(FLEET), { maintenance_available: false, maintenance_detail: detail });
    await setUpServers(page, { servers: answer });
    const calls = await mockMaintenance(page, answer);
    await go(page, PAGE);
    const button = toggle(page, "ocp-dell-r660-site1-node-01");
    await expect(button).toHaveAttribute("aria-disabled", "true");
    await expect(button).toHaveAttribute("title", detail);
    // Playwright waits for an aria-disabled button: force the click, which does nothing
    await button.click({ force: true });
    await toggle(page, "ocp-dell-r660-site1-node-03").click({ force: true });
    await expect(dialog(page)).toHaveCount(0);
    expect(calls).toHaveLength(0);
  });

  test("an unanswered change says so in the dialog, and is not sent again", async ({ page }) => {
    const answer = mockServers(structuredClone(FLEET));
    await setUpServers(page, { servers: answer });
    const detail = "server-scan did not answer putting srv_ocp-dell-r660-site1-node-01 into maintenance: it may have changed. Look at the row before trying again.";
    const calls = await mockMaintenance(page, answer, (route) => fulfillProblem(route, 504, "AMBIGUOUS_WRITE", detail));
    await go(page, PAGE);
    await toggle(page, "ocp-dell-r660-site1-node-01").click();
    await dialog(page).getByRole("textbox", { name: /^Why is it going/ }).fill("PSU");
    await dialog(page).getByRole("button", { name: "Start maintenance" }).click();
    await expect(dialog(page).getByRole("alert")).toHaveText(detail);
    expect(calls).toHaveLength(1);
    // Ending one that fails is a toast
    await dialog(page).getByRole("button", { name: "Cancel" }).click();
    await toggle(page, "ocp-dell-r660-site1-node-03").click();
    await expect(page.getByText(/Maintenance on ocp-dell-r660-site1-node-03 was not ended/)).toBeVisible();
    expect(calls).toHaveLength(2);
  });
});

test.describe("A row's Fetch now", () => {
  const fetchNow = (page: Page, name: string) => row(page, name).getByTestId("ss-row-fetch-now");
  const NODE = "ocp-dell-r660-site1-node-01";

  test("reads that one server from its manager, says so with its name, and the rows are read again", async ({ page }) => {
    const { reads } = await setUpServers(page);
    const calls = await mockFetchNow(page, [nodeRecord()]);
    await go(page, PAGE);
    await expect(rows(page)).toHaveCount(12);
    const before = reads();
    await expect(fetchNow(page, NODE)).toHaveAccessibleName(`Fetch data of ${NODE} now`);
    await fetchNow(page, NODE).click();
    await expect(page.getByText(`Fetched ${NODE}`)).toBeVisible();
    await expect(page.getByText("From OPENMANAGE", { exact: true })).toBeVisible();
    await expect.poll(() => reads()).toBeGreaterThan(before);
    expect(calls).toEqual([`srv_${NODE}`]);
  });

  test("a failure is a toast in the API's words, sent once", async ({ page }) => {
    await setUpServers(page);
    const words = "server-scan: The ONEVIEW manager no longer reports it; the stored data is unchanged.";
    const calls = await mockFetchNow(page, (route) => fulfillProblem(route, 409, "SERVER_REFRESH_REFUSED", words));
    await go(page, PAGE);
    await fetchNow(page, "hpe-dl380-site2-stale-10").click();
    await expect(page.getByText(`hpe-dl380-site2-stale-10: ${words}`)).toBeVisible();
    expect(calls).toHaveLength(1);
  });

  test("where the deployment does not offer it (DAY1_SERVER_SCAN_REFRESH) there is no column at all", async ({ page }) => {
    const off = { refresh_enabled: false, refresh_available: false, refresh_detail: "Fetch now is off in this deployment." };
    await setUpServers(page, { servers: mockServers(FLEET, off) });
    await go(page, PAGE);
    await expect(rows(page)).toHaveCount(12);
    await expect(page.getByRole("table", { name: "Servers" }).locator("thead th")).toHaveText([
      "Name", "BMC", "Installation", "MCE", "Cluster", "Model", "State", "Maintenance",
    ]);
    await expect(page.getByTestId("ss-row-fetch-now")).toHaveCount(0);
  });

  test("without server-scan's admin token every row's is greyed with day1's line, and sends nothing", async ({ page }) => {
    const why = "Fetch now needs server-scan's admin token: add the key admin-token to the server-scan Secret and restart day1 (SERVER_SCAN_ADMIN_TOKEN).";
    await setUpServers(page, { servers: mockServers(FLEET, { refresh_available: false, refresh_detail: why }) });
    const calls = await mockFetchNow(page, [nodeRecord()]);
    await go(page, PAGE);
    await expect(fetchNow(page, NODE)).toHaveAttribute("aria-disabled", "true");
    await expect(fetchNow(page, NODE)).toHaveAttribute("title", why);
    await fetchNow(page, NODE).click({ force: true });
    expect(calls).toEqual([]);
  });
});
